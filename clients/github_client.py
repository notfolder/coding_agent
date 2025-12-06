"""GitHub APIクライアント.

このモジュールは、GitHub APIを使用してPull Request、Issue、ラベル等の
操作を行うためのクライアントクラスを提供します。
"""
from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)


class GithubClient:
    """GitHub APIクライアント.

    GitHub APIを使用してPull Request、Issue、ラベル等を操作するための
    クライアントクラスです。Personal Access Tokenによる認証を行います。
    """

    def __init__(self, token: str, api_url: str = "https://api.github.com") -> None:
        """GitHubクライアントを初期化する.

        Args:
            token: GitHub Personal Access Token（必須）
            api_url: GitHub APIのベースURL（デフォルト: https://api.github.com）

        Raises:
            ValueError: トークンがNoneまたは空文字列の場合

        """
        # トークンが設定されていない場合はエラー
        if not token:
            error_msg = "GitHub Personal Access Token is required"
            raise ValueError(error_msg)
        
        self.token = token
        self.api_url = api_url

        # APIリクエスト用のヘッダーを設定
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
        }

    def get_pull_request_labels(self, owner: str, repo: str, pull_number: int) -> list[str]:
        """指定したPull Requestのラベル一覧を取得する.

        Args:
            owner: リポジトリのオーナー名
            repo: リポジトリ名
            pull_number: Pull Request番号

        Returns:
            ラベル名のリスト

        Raises:
            requests.HTTPError: APIリクエストが失敗した場合

        """
        # GitHub APIのエンドポイントURL構築
        url = f"{self.api_url}/repos/{owner}/{repo}/issues/{pull_number}"

        # APIリクエストの実行
        response = requests.get(url, headers=self.headers, timeout=30)
        response.raise_for_status()

        # レスポンスからラベル名を抽出
        issue = response.json()
        return [label["name"] for label in issue.get("labels", [])]

    def list_pull_requests_with_label(
        self,
        owner: str,
        repo: str,
        label: str,
        state: str = "open",
        *,
        per_page: int = 100,
        max_pages: int = 20,
    ) -> list[dict[str, Any]]:
        """指定したラベルが付いているPull Requestの一覧を取得する.

        Args:
            owner: リポジトリのオーナー名
            repo: リポジトリ名
            label: 検索対象のラベル名
            state: Pull Requestの状態("open", "closed", "all")

        Returns:
            条件に一致するPull Requestの情報リスト

        Raises:
            requests.HTTPError: APIリクエストが失敗した場合

        """
        # Pull Request一覧取得のAPIエンドポイント
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls"
        params = {"state": state}

        # Pull Request一覧をページングしながら取得
        pulls = self._fetch_paginated_list(url, params, per_page, max_pages)

        # 指定されたラベルが付いているPull Requestをフィルタリング
        result = []
        for pr in pulls:
            # 各Pull Requestのラベルを取得
            labels = self.get_pull_request_labels(owner, repo, pr["number"])

            # 指定されたラベルが含まれている場合は結果に追加
            if label in labels:
                pr["labels"] = labels
                result.append(pr)

        return result

    def list_branches(
        self, owner: str, repo: str, per_page: int = 100, max_pages: int = 20,
    ) -> list[dict[str, Any]]:
        """リポジトリのブランチ一覧を取得する.

        Args:
            owner: リポジトリのオーナー名
            repo: リポジトリ名
            per_page: 1ページあたりの件数
            max_pages: 最大ページ数

        Returns:
            ブランチ情報のリスト

        """
        url = f"{self.api_url}/repos/{owner}/{repo}/branches"
        return self._fetch_paginated_list(url, {}, per_page, max_pages)

    def create_branch(
        self, owner: str, repo: str, branch: str, sha: str | None = None,
    ) -> dict[str, Any]:
        """新しいブランチを作成する.

        Args:
            owner: リポジトリのオーナー名
            repo: リポジトリ名
            branch: ブランチ名
            sha: ブランチの基点となるコミットSHA（Noneの場合はデフォルトブランチのHEAD）

        Returns:
            作成されたリファレンス情報

        """
        # デフォルトブランチのSHAを取得
        if sha is None:
            repo_info_url = f"{self.api_url}/repos/{owner}/{repo}"
            repo_response = requests.get(repo_info_url, headers=self.headers, timeout=30)
            repo_response.raise_for_status()
            default_branch = repo_response.json()["default_branch"]

            branch_url = f"{self.api_url}/repos/{owner}/{repo}/git/ref/heads/{default_branch}"
            branch_response = requests.get(branch_url, headers=self.headers, timeout=30)
            branch_response.raise_for_status()
            sha = branch_response.json()["object"]["sha"]

        # ブランチを作成
        url = f"{self.api_url}/repos/{owner}/{repo}/git/refs"
        data = {"ref": f"refs/heads/{branch}", "sha": sha}
        response = requests.post(url, headers=self.headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()

    def create_or_update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        message: str,
        content: str,
        branch: str,
        sha: str | None = None,
    ) -> dict[str, Any]:
        """ファイルを作成または更新する.

        Args:
            owner: リポジトリのオーナー名
            repo: リポジトリ名
            path: ファイルパス
            message: コミットメッセージ
            content: ファイル内容
            branch: ブランチ名
            sha: 更新時の既存ファイルのSHA（新規作成時はNone）

        Returns:
            作成/更新されたファイル情報

        """
        import base64

        url = f"{self.api_url}/repos/{owner}/{repo}/contents/{path}"
        encoded_content = base64.b64encode(content.encode()).decode()
        data: dict[str, Any] = {
            "message": message,
            "content": encoded_content,
            "branch": branch,
        }
        if sha:
            data["sha"] = sha

        response = requests.put(url, headers=self.headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()

    def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
        draft: bool = False,
    ) -> dict[str, Any]:
        """Pull Requestを作成する.

        Args:
            owner: リポジトリのオーナー名
            repo: リポジトリ名
            title: PR タイトル
            body: PR 本文
            head: ソースブランチ名
            base: ターゲットブランチ名
            draft: ドラフトPRとして作成するか

        Returns:
            作成されたPull Request情報

        """
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls"
        data: dict[str, Any] = {
            "title": title,
            "body": body,
            "head": head,
            "base": base,
            "draft": draft,
        }
        response = requests.post(url, headers=self.headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()

    def update_pull_request(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        title: str | None = None,
        body: str | None = None,
    ) -> dict[str, Any]:
        """Pull Requestを更新する.

        Args:
            owner: リポジトリのオーナー名
            repo: リポジトリ名
            pull_number: Pull Request番号
            title: 新しいタイトル（Noneの場合は変更なし）
            body: 新しい本文（Noneの場合は変更なし）

        Returns:
            更新されたPull Request情報

        """
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pull_number}"
        data: dict[str, Any] = {}
        if title:
            data["title"] = title
        if body is not None:
            data["body"] = body

        response = requests.patch(url, headers=self.headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()

    def add_issue_labels(
        self, owner: str, repo: str, issue_number: int, labels: list[str],
    ) -> list[dict[str, Any]]:
        """IssueまたはPull Requestにラベルを追加する.

        Args:
            owner: リポジトリのオーナー名
            repo: リポジトリ名
            issue_number: IssueまたはPull Request番号
            labels: 追加するラベル名のリスト

        Returns:
            追加後のラベル情報のリスト

        """
        url = f"{self.api_url}/repos/{owner}/{repo}/issues/{issue_number}/labels"
        data = {"labels": labels}
        response = requests.post(url, headers=self.headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()

    def update_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        assignees: list[str] | None = None,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """IssueまたはPull Requestを更新する.

        Args:
            owner: リポジトリのオーナー名
            repo: リポジトリ名
            issue_number: IssueまたはPull Request番号
            assignees: アサインするユーザー名のリスト
            labels: 設定するラベル名のリスト

        Returns:
            更新されたIssue情報

        """
        url = f"{self.api_url}/repos/{owner}/{repo}/issues/{issue_number}"
        data: dict[str, Any] = {}
        if assignees:
            data["assignees"] = assignees
        if labels:
            data["labels"] = labels

        response = requests.patch(url, headers=self.headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()

    def delete_branch(
        self, owner: str, repo: str, branch: str,
    ) -> None:
        """ブランチを削除する.

        Args:
            owner: リポジトリのオーナー名
            repo: リポジトリ名
            branch: ブランチ名

        """
        url = f"{self.api_url}/repos/{owner}/{repo}/git/refs/heads/{branch}"
        response = requests.delete(url, headers=self.headers, timeout=30)
        response.raise_for_status()

    def add_comment_to_pull_request(
        self, owner: str, repo: str, pull_number: int, body: str,
    ) -> dict[str, Any]:
        """Pull Requestにコメントを追加する.

        Args:
            owner: リポジトリのオーナー名
            repo: リポジトリ名
            pull_number: Pull Request番号
            body: コメント本文

        Returns:
            作成されたコメントの情報

        Raises:
            requests.HTTPError: APIリクエストが失敗した場合

        """
        # コメント追加のAPIエンドポイント
        url = f"{self.api_url}/repos/{owner}/{repo}/issues/{pull_number}/comments"
        data = {"body": body}

        # コメントを投稿
        response = requests.post(url, headers=self.headers, json=data, timeout=30)
        response.raise_for_status()

        return response.json()

    def update_issue_comment(
        self, owner: str, repo: str, comment_id: int, body: str,
    ) -> dict[str, Any]:
        """既存のIssue/Pull Requestコメントを更新する.

        Args:
            owner: リポジトリのオーナー名
            repo: リポジトリ名
            comment_id: コメントID
            body: 更新後のコメント本文

        Returns:
            更新されたコメントの情報

        Raises:
            requests.HTTPError: APIリクエストが失敗した場合

        """
        # コメント更新のAPIエンドポイント
        url = f"{self.api_url}/repos/{owner}/{repo}/issues/comments/{comment_id}"
        data = {"body": body}

        # コメントを更新
        response = requests.patch(url, headers=self.headers, json=data, timeout=30)
        response.raise_for_status()

        return response.json()

    def add_comment_to_issue(
        self, owner: str, repo: str, issue_number: int, body: str,
    ) -> dict[str, Any]:
        """Issueにコメントを追加する.

        Args:
            owner: リポジトリのオーナー名
            repo: リポジトリ名
            issue_number: Issue番号
            body: コメント本文

        Returns:
            作成されたコメントの情報

        Raises:
            requests.HTTPError: APIリクエストが失敗した場合

        """
        # IssueとPull Requestは同じエンドポイントを使用
        return self.add_comment_to_pull_request(owner, repo, issue_number, body)

    def update_pull_request_labels(
        self, owner: str, repo: str, pull_number: int, labels: list[str],
    ) -> dict[str, Any]:
        """Pull Requestのラベルを更新する.

        Args:
            owner: リポジトリのオーナー名
            repo: リポジトリ名
            pull_number: Pull Request番号
            labels: 設定するラベル名のリスト

        Returns:
            更新されたラベルの情報

        Raises:
            requests.HTTPError: APIリクエストが失敗した場合

        """
        # ラベル更新のAPIエンドポイント
        url = f"{self.api_url}/repos/{owner}/{repo}/issues/{pull_number}/labels"
        data = labels

        # ラベルを更新
        response = requests.put(url, headers=self.headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()

    def update_issue_labels(
        self, owner: str, repo: str, issue_number: int, labels: list[str],
    ) -> dict[str, Any]:
        """指定したIssueのラベルを更新する.

        Args:
            owner: リポジトリのオーナー名
            repo: リポジトリ名
            issue_number: Issue番号
            labels: 設定するラベル名のリスト

        Returns:
            更新されたラベルの情報

        Raises:
            requests.HTTPError: APIリクエストが失敗した場合

        """
        # Issue ラベル更新のAPIエンドポイント
        url = f"{self.api_url}/repos/{owner}/{repo}/issues/{issue_number}/labels"
        data = labels

        # ラベルを更新
        response = requests.put(url, headers=self.headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_pull_request_comments(
        self, owner: str, repo: str, pull_number: int,
    ) -> list[dict[str, Any]]:
        """指定したPull Requestのレビューコメントとタイムラインコメントの両方を取得する.

        submitted_at(レビュー)・created_at(イシュー)で時系列ソートして返します。

        Args:
            owner: リポジトリのオーナー名
            repo: リポジトリ名
            pull_number: Pull Request番号

        Returns:
            時系列順にソートされたコメントのリスト

        Raises:
            requests.HTTPError: APIリクエストが失敗した場合

        """
        # レビューコメントを取得
        review_comments = self.get_reviews_with_comments(owner, repo, pull_number)

        # タイムラインコメント(Issueコメント)を取得
        url_issue = f"{self.api_url}/repos/{owner}/{repo}/issues/{pull_number}/comments"
        issue_comments_raw = self._fetch_paginated_list(
            url_issue,
            {},
            per_page=200,
            max_pages=20,
        )

        # 不要なURLフィールドを削除
        issue_comments = [self.remove_url_fields(c) for c in issue_comments_raw]

        # レビューコメントとIssueコメントをマージして時系列ソート
        merged = [
            {**r, "type": "review", "sort_key": r.get("submitted_at")}
            for r in review_comments
        ] + [
            {**c, "type": "issue_comment", "sort_key": c.get("created_at")}
            for c in issue_comments
        ]

        # sort_keyで昇順ソート
        merged.sort(key=lambda x: (x["sort_key"] or ""))

        # sort_keyを削除して返す
        return [{k: v for k, v in d.items() if k != "sort_key"} for d in merged]

    def get_reviews_with_comments(
        self, owner: str, repo: str, pull_number: int,
    ) -> list[dict[str, Any]]:
        """指定したPull Requestの各レビューごとに、そのレビューに紐づくコメントをまとめて返す.

        Args:
            owner: リポジトリのオーナー名
            repo: リポジトリ名
            pull_number: Pull Request番号

        Returns:
            レビューとコメントが紐づけられたデータのリスト

        Raises:
            requests.HTTPError: APIリクエストが失敗した場合

        """
        # レビュー一覧を取得
        url_reviews = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pull_number}/reviews"
        reviews_raw = self._fetch_paginated_list(
            url_reviews,
            {},
            per_page=100,
            max_pages=20,
        )
        reviews = [self.remove_url_fields(r) for r in reviews_raw]

        # レビューコメント一覧を取得
        url_comments = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pull_number}/comments"
        comments_raw = self._fetch_paginated_list(
            url_comments,
            {},
            per_page=200,
            max_pages=20,
        )
        comments = [self.remove_url_fields(c) for c in comments_raw]

        # review_idごとにコメントをまとめる
        review_id_to_comments: dict[int, list[dict[str, Any]]] = {}
        for comment in comments:
            review_id = comment.get("pull_request_review_id")
            if review_id:
                review_id_to_comments.setdefault(review_id, []).append(comment)

        # 各レビューにコメントを紐付け
        for review in reviews:
            review["comments"] = review_id_to_comments.get(review.get("id"), [])

        return reviews

    def remove_url_fields(
        self,
        obj: object,
    ) -> object:
        """辞書またはリストから再帰的にURLのみを含むフィールドを削除する.

        APIレスポンスから不要なURLフィールドを削除し、
        データサイズを削減するために使用されます。

        Args:
            obj: 処理対象のオブジェクト(辞書、リスト、またはその他)

        Returns:
            URLフィールドが削除されたオブジェクト

        """

        def is_url(val: object) -> bool:
            """値がURL文字列かどうかを判定する."""
            return isinstance(val, str) and (
                val.startswith(("http://", "https://"))
            )

        if isinstance(obj, dict):
            return {
                k: self.remove_url_fields(v)
                for k, v in obj.items()
                if not (is_url(v) and isinstance(v, str))
            }
        return obj

    def get_pull_request(self, owner: str, repo: str, pull_number: int) -> dict[str, Any]:
        """Pull Request単体を取得する.

        Args:
            owner: リポジトリのオーナー名
            repo: リポジトリ名
            pull_number: Pull Request番号

        Returns:
            Pull Requestの詳細情報(ラベル情報を含む)

        Raises:
            requests.HTTPError: APIリクエストが失敗した場合

        """
        # Pull Request取得のAPIエンドポイント
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pull_number}"
        headers = self.headers.copy()

        # Pull Request情報を取得
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        pr = resp.json()

        # Pull Requestのラベルを取得して追加
        labels = self.get_pull_request_labels(owner, repo, pr["number"])
        pr["labels"] = labels if isinstance(labels, list) else []

        return pr

    def search_issues_and_prs(
        self,
        query: str,
        sort: str | None = None,
        order: str | None = None,
        per_page: int = 200,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """GitHubのSearch APIでIssueとPull Request両方を検索する汎用メソッド.

        Args:
            query: 検索クエリ
            sort: ソート条件
            order: ソート順序("asc" または "desc")
            per_page: 1ページあたりの件数
            page: ページ番号

        Returns:
            検索結果のリスト

        Raises:
            requests.HTTPError: APIリクエストが失敗した場合

        """
        # Search API のエンドポイント
        url = f"{self.api_url}/search/issues"
        return self._fetch_search_results(url, query, sort, order, per_page, page)

    def search_pull_requests(
        self,
        query: str,
        sort: str | None = None,
        order: str | None = None,
        per_page: int = 200,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """Pull Requestのみを検索する.

        Args:
            query: 検索クエリ
            sort: ソート条件
            order: ソート順序
            per_page: 1ページあたりの件数
            page: ページ番号

        Returns:
            Pull Requestの検索結果のリスト

        """
        # Pull Request限定の検索クエリに変換
        if "type:pr" not in query:
            query = query.strip() + " type:pr"

        # 検索実行とPull Requestのフィルタリング
        items = self.search_issues_and_prs(query, sort, order, per_page, page)
        return [item for item in items if "pull_request" in item]

    def search_issues(
        self,
        query: str,
        sort: str | None = None,
        order: str | None = None,
        per_page: int = 200,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """Issueのみを検索する.

        Args:
            query: 検索クエリ
            sort: ソート条件
            order: ソート順序
            per_page: 1ページあたりの件数
            page: ページ番号

        Returns:
            Issueの検索結果のリスト

        """
        # Issue限定の検索クエリに変換
        if "type:issue" not in query:
            query = query.strip() + " type:issue"

        # 検索実行とIssueのフィルタリング
        items = self.search_issues_and_prs(query, sort, order, per_page, page)
        return [item for item in items if "pull_request" not in item]

    def _fetch_paginated_list(
        self,
        url: str,
        params: dict[str, Any],
        per_page: int,
        max_pages: int,
    ) -> list[dict[str, Any]]:
        """GitHubの標準REST APIでページングされるリストを全件取得する."""
        items: list[dict[str, Any]] = []
        page_number: int = 1

        # Linkヘッダーを使わず、ページ数と件数で終了条件を判定
        while page_number <= max_pages:
            page_params = dict(params)
            page_params["per_page"] = per_page
            page_params["page"] = page_number

            try:
                response = requests.get(url, headers=self.headers, params=page_params, timeout=30)
                response.raise_for_status()
                page_items = response.json()
            except requests.exceptions.RequestException as e:
                logger.error(
                    "GitHub API request failed: url=%s, params=%s, error=%s",
                    url, page_params, e
                )
                raise

            if not isinstance(page_items, list) or not page_items:
                break

            items.extend(page_items)

            if len(page_items) < per_page:
                break

            page_number += 1

        return items

    def _fetch_search_results(
        self,
        url: str,
        query: str,
        sort: str | None,
        order: str | None,
        per_page: int,
        page: int,
        *,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        """Search APIで複数ページに跨る結果を収集する."""
        aggregated: list[dict[str, Any]] = []
        current_page: int = page
        pages_fetched: int = 0

        # Search API固有のtotal_countなどを利用してループを制御
        while pages_fetched < max_pages:
            params = {"q": query, "per_page": per_page, "page": current_page}
            if sort:
                params["sort"] = sort
            if order:
                params["order"] = order

            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
            except requests.exceptions.RequestException as e:
                logger.error(
                    "GitHub Search API request failed: url=%s, params=%s, error=%s",
                    url, params, e
                )
                raise

            page_items = data.get("items", [])
            if not page_items:
                break

            aggregated.extend(page_items)

            total_count = data.get("total_count")
            if isinstance(total_count, int) and total_count <= len(aggregated):
                break

            if data.get("incomplete_results") is True:
                break

            if not isinstance(total_count, int) and len(page_items) < per_page:
                break

            current_page += 1
            pages_fetched += 1

        return aggregated

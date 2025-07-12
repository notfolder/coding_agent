"""GitHub APIクライアント.

このモジュールは、GitHub APIを使用してPull Request、Issue、ラベル等の
操作を行うためのクライアントクラスを提供します。
"""
from __future__ import annotations

import os
from typing import Any

import requests


class GithubClient:
    """GitHub APIクライアント.

    GitHub APIを使用してPull Request、Issue、ラベル等を操作するための
    クライアントクラスです。Personal Access Tokenによる認証を行います。
    """

    def __init__(self, token: str | None = None, api_url: str | None = None) -> None:
        """GitHubクライアントを初期化する.

        Args:
            token: GitHub Personal Access Token。Noneの場合は環境変数から取得
            api_url: GitHub APIのベースURL。Noneの場合はデフォルトを使用

        Raises:
            ValueError: トークンが設定されていない場合

        """
        # トークンの設定(引数または環境変数から取得)
        self.token = token or os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")

        # APIのベースURLの設定(デフォルト: https://api.github.com)
        self.api_url = api_url or "https://api.github.com"

        # トークンが設定されていない場合はエラー
        if not self.token:
            error_msg = "GITHUB_PERSONAL_ACCESS_TOKEN is not set"
            raise ValueError(error_msg)

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
        self, owner: str, repo: str, label: str, state: str = "open",
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
        params = {"state": state, "per_page": 100}

        # Pull Request一覧を取得
        response = requests.get(url, headers=self.headers, params=params, timeout=30)
        response.raise_for_status()
        pulls = response.json()

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
        resp_issue = requests.get(
            url_issue, headers=self.headers, params={"per_page": 200}, timeout=30,
        )
        resp_issue.raise_for_status()
        issue_comments_raw = resp_issue.json()

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
        resp_reviews = requests.get(
            url_reviews, headers=self.headers, params={"per_page": 100}, timeout=30,
        )
        resp_reviews.raise_for_status()
        reviews_raw = resp_reviews.json()
        reviews = [self.remove_url_fields(r) for r in reviews_raw]

        # レビューコメント一覧を取得
        url_comments = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pull_number}/comments"
        resp_comments = requests.get(
            url_comments, headers=self.headers, params={"per_page": 200}, timeout=30,
        )
        resp_comments.raise_for_status()
        comments_raw = resp_comments.json()
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

    def remove_url_fields(self, obj: Any) -> Any:
        """辞書またはリストから再帰的にURLのみを含むフィールドを削除する.

        APIレスポンスから不要なURLフィールドを削除し、
        データサイズを削減するために使用されます。

        Args:
            obj: 処理対象のオブジェクト(辞書、リスト、またはその他)

        Returns:
            URLフィールドが削除されたオブジェクト

        """

        def is_url(val: Any) -> bool:
            """値がURL文字列かどうかを判定する."""
            return isinstance(val, str) and (
                val.startswith(("http://", "https://"))
            )

        if isinstance(obj, dict):
            # 辞書の場合:URLでない値のみを残して再帰的に処理
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
        params = {"q": query, "per_page": per_page, "page": page}

        # ソート条件とソート順序を設定
        if sort:
            params["sort"] = sort
        if order:
            params["order"] = order

        # 検索実行
        response = requests.get(url, headers=self.headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        return data.get("items", [])

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

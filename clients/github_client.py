import os

import requests


class GithubClient:
    def __init__(self, token=None, api_url=None):
        self.token = token or os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
        self.api_url = api_url or "https://api.github.com"
        if not self.token:
            raise ValueError("GITHUB_PERSONAL_ACCESS_TOKEN is not set")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
        }

    def get_pull_request_labels(self, owner, repo, pull_number):
        """指定したPull Requestのラベル一覧を取得する
        """
        url = f"{self.api_url}/repos/{owner}/{repo}/issues/{pull_number}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        issue = response.json()
        return [l["name"] for l in issue.get("labels", [])]

    def list_pull_requests_with_label(self, owner, repo, label, state="open"):
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls"
        params = {"state": state, "per_page": 100}
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        pulls = response.json()
        result = []
        for pr in pulls:
            labels = self.get_pull_request_labels(owner, repo, pr["number"])
            if label in labels:
                pr["labels"] = labels
                result.append(pr)
        return result

    def add_comment_to_pull_request(self, owner, repo, pull_number, body):
        url = f"{self.api_url}/repos/{owner}/{repo}/issues/{pull_number}/comments"
        data = {"body": body}
        response = requests.post(url, headers=self.headers, json=data)
        response.raise_for_status()
        return response.json()

    def update_pull_request_labels(self, owner, repo, pull_number, labels):
        url = f"{self.api_url}/repos/{owner}/{repo}/issues/{pull_number}/labels"
        data = labels
        response = requests.put(url, headers=self.headers, json=data)
        response.raise_for_status()
        return response.json()

    def update_issue_labels(self, owner, repo, issue_number, labels):
        """指定したIssueのラベルを更新する
        """
        url = f"{self.api_url}/repos/{owner}/{repo}/issues/{issue_number}/labels"
        data = labels
        response = requests.put(url, headers=self.headers, json=data)
        response.raise_for_status()
        return response.json()

    def get_pull_request_comments(self, owner, repo, pull_number):
        """指定したPull Requestのレビューコメントとタイムラインコメントの両方を取得し、
        submitted_at（レビュー）・created_at（イシュー）で時系列ソートして返す
        """
        # レビューコメント
        review_comments = self.get_reviews_with_comments(owner, repo, pull_number)
        # タイムラインコメント
        url_issue = f"{self.api_url}/repos/{owner}/{repo}/issues/{pull_number}/comments"
        resp_issue = requests.get(url_issue, headers=self.headers, params={"per_page": 200})
        resp_issue.raise_for_status()
        issue_comments_raw = resp_issue.json()
        issue_comments = [self.remove_url_fields(c) for c in issue_comments_raw]

        merged = [
            {**r, "type": "review", "sort_key": r.get("submitted_at")} for r in review_comments
        ] + [
            {**c, "type": "issue_comment", "sort_key": c.get("created_at")} for c in issue_comments
        ]
        # sort_keyで昇順ソート
        merged.sort(key=lambda x: (x["sort_key"] or ""))
        merged = [{k: v for k, v in d.items() if k != "sort_key"} for d in merged]
        return merged

    def get_reviews_with_comments(self, owner, repo, pull_number):
        """指定したPull Requestの各レビューごとに、そのレビューに紐づくコメントをまとめて返す。
        """
        # レビュー一覧
        url_reviews = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pull_number}/reviews"
        resp_reviews = requests.get(url_reviews, headers=self.headers, params={"per_page": 100})
        resp_reviews.raise_for_status()
        reviews_raw = resp_reviews.json()
        reviews = [self.remove_url_fields(r) for r in reviews_raw]

        # レビューコメント一覧
        url_comments = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pull_number}/comments"
        resp_comments = requests.get(url_comments, headers=self.headers, params={"per_page": 200})
        resp_comments.raise_for_status()
        comments_raw = resp_comments.json()
        comments = [self.remove_url_fields(c) for c in comments_raw]

        # review_idごとにコメントをまとめる
        review_id_to_comments = {}
        for comment in comments:
            review_id = comment.get("pull_request_review_id")
            if review_id:
                review_id_to_comments.setdefault(review_id, []).append(comment)

        # 各レビューにコメントを紐付け
        for review in reviews:
            review["comments"] = review_id_to_comments.get(review.get("id"), [])

        return reviews

    def remove_url_fields(self, obj):
        """辞書またはリストから再帰的にURLのみを含むフィールドを削除する
        """

        def is_url(val):
            return isinstance(val, str) and (
                val.startswith("http://") or val.startswith("https://")
            )

        if isinstance(obj, dict):
            return {
                k: self.remove_url_fields(v)
                for k, v in obj.items()
                if not (is_url(v) and isinstance(v, str))
            }
        return obj

    def get_pull_request(self, owner, repo, pull_number):
        """Pull Request単体取得"""
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pull_number}"
        headers = self.headers.copy()
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        pr = resp.json()
        # Pull Requestのラベルを取得して追加
        labels = self.get_pull_request_labels(owner, repo, pr["number"])
        pr["labels"] = labels if isinstance(labels, list) else []
        return pr

    def search_issues_and_prs(self, query, sort=None, order=None, per_page=200, page=1):
        """GitHubのSearch APIでIssueとPull Request両方を検索する汎用メソッド
        :param query: 検索クエリ
        :param sort: ソート条件
        :param order: asc/desc
        :param per_page: 1ページあたりの件数
        :param page: ページ番号
        :return: 検索結果（全件）
        """
        url = f"{self.api_url}/search/issues"
        params = {"q": query, "per_page": per_page, "page": page}
        if sort:
            params["sort"] = sort
        if order:
            params["order"] = order
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("items", [])

    def search_pull_requests(self, query, sort=None, order=None, per_page=200, page=1):
        """Pull Requestのみを検索
        """
        if "type:pr" not in query:
            query = query.strip() + " type:pr"
        items = self.search_issues_and_prs(query, sort, order, per_page, page)
        return [item for item in items if "pull_request" in item]

    def search_issues(self, query, sort=None, order=None, per_page=200, page=1):
        """Issueのみを検索
        """
        if "type:issue" not in query:
            query = query.strip() + " type:issue"
        items = self.search_issues_and_prs(query, sort, order, per_page, page)
        return [item for item in items if "pull_request" not in item]

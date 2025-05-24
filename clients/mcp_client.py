# coding: utf-8
import os
import requests
from typing import List, TypedDict

class Issue(TypedDict):
    number: int
    title: str
    body: str

class MCPClient:
    def __init__(self, config):
        self.server_url = config['mcp']['server_url']
        self.api_key = os.environ.get(config['mcp']['api_key_env'])
        self.owner = config['github']['owner']
        self.repo = config['github']['repo']
        self.headers = {'Authorization': f'Bearer {self.api_key}'}

    def get_issues(self, label: str) -> List[Issue]:
        url = f"{self.server_url}/repos/{self.owner}/{self.repo}/issues"
        params = {"labels": label}
        resp = requests.get(url, headers=self.headers, params=params)
        resp.raise_for_status()
        return resp.json()

    def update_issue(self, number: int, remove_label: str) -> None:
        url = f"{self.server_url}/repos/{self.owner}/{self.repo}/issues/{number}"
        data = {"remove_labels": [remove_label]}
        resp = requests.patch(url, headers=self.headers, json=data)
        resp.raise_for_status()

    def add_issue_comment(self, number: int, comment: str) -> None:
        url = f"{self.server_url}/repos/{self.owner}/{self.repo}/issues/{number}/comments"
        data = {"body": comment}
        resp = requests.post(url, headers=self.headers, json=data)
        resp.raise_for_status()

    def call_tool(self, tool: str, args: dict) -> dict:
        url = f"{self.server_url}/tool/{tool}"
        data = args.copy()
        data['owner'] = self.owner
        data['repo'] = self.repo
        resp = requests.post(url, headers=self.headers, json=data)
        resp.raise_for_status()
        return resp.json()

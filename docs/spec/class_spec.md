# クラス設計・関係図（coding_agent プロジェクト）

## 概要
本プロジェクトは、GitHub/GitLabのMCPサーバーと連携し、タスク（Issue/PR/MR）をLLMで処理するエージェントです。

---

## クラス一覧・継承/保合/呼び出し関係

### [抽象基底クラス]
- TaskKey (handlers/task_key.py)
    - GitHubIssueTaskKey
    - GitHubPullRequestTaskKey
    - GitLabIssueTaskKey
    - GitLabMergeRequestTaskKey
- Task (handlers/task.py)
    - TaskGitHubIssue (handlers/task_getter_github.py)
    - TaskGitHubPullRequest (handlers/task_getter_github.py)
    - TaskGitLabIssue (handlers/task_getter_gitlab.py)
    - TaskGitLabMergeRequest (handlers/task_getter_gitlab.py)
- TaskGetter (handlers/task_getter.py)
    - TaskGetterFromGitHub (handlers/task_getter_github.py)
    - TaskGetterFromGitLab (handlers/task_getter_gitlab.py)
- TaskFactory (handlers/task_factory.py)
    - GitHubTaskFactory
    - GitLabTaskFactory
- TaskQueue (queueing.py)
    - InMemoryTaskQueue

### [主要クラス]
- TaskHandler (handlers/task_handler.py)
- MCPToolClient (clients/mcp_tool_client.py)
- GithubClient (clients/github_client.py)
- GitlabClient (clients/gitlab_client.py)
- LLMクライアント群 (clients/lm_client.py, openai_client.py, lmstudio_client.py, ollama_client.py)
- FileLock (filelock_util.py)

---

## 保合・呼び出し関係
- main.py
    - TaskGetter.factory で TaskGetterFromGitHub / TaskGetterFromGitLab を生成
    - TaskGetter.get_task_list() で TaskKey のリストを生成
    - TaskKey を InMemoryTaskQueue にput
    - consume_tasks で TaskGetter.from_task_key(dict) で Taskインスタンス復元
    - TaskHandler.handle(task) でタスク処理
- TaskGitHubIssue/TaskGitHubPullRequest
    - MCPToolClient, GithubClient を利用
- TaskGitLabIssue/TaskGitLabMergeRequest
    - MCPToolClient, GitlabClient を利用
- TaskFactory
    - TaskKey から Task を生成（from_task_keyの実装に近い役割）
- InMemoryTaskQueue
    - TaskKey(dict)をput/get
- FileLock
    - プロセス排他制御

---

## Mermaid クラス図
```mermaid
classDiagram
    class TaskKey {
        <<abstract>>
        +to_dict()
        +from_dict()
    }
    class GitHubIssueTaskKey
    class GitHubPullRequestTaskKey
    class GitLabIssueTaskKey
    class GitLabMergeRequestTaskKey
    TaskKey <|-- GitHubIssueTaskKey
    TaskKey <|-- GitHubPullRequestTaskKey
    TaskKey <|-- GitLabIssueTaskKey
    TaskKey <|-- GitLabMergeRequestTaskKey

    class Task {
        <<abstract>>
        +prepare()
        +get_prompt()
        +comment()
        +finish()
    }
    class TaskGitHubIssue
    class TaskGitHubPullRequest
    class TaskGitLabIssue
    class TaskGitLabMergeRequest
    Task <|-- TaskGitHubIssue
    Task <|-- TaskGitHubPullRequest
    Task <|-- TaskGitLabIssue
    Task <|-- TaskGitLabMergeRequest

    class TaskGetter {
        <<abstract>>
        +get_task_list()
        +from_task_key()
    }
    class TaskGetterFromGitHub
    class TaskGetterFromGitLab
    TaskGetter <|-- TaskGetterFromGitHub
    TaskGetter <|-- TaskGetterFromGitLab

    class TaskFactory {
        <<abstract>>
        +create_task()
    }
    class GitHubTaskFactory
    class GitLabTaskFactory
    TaskFactory <|-- GitHubTaskFactory
    TaskFactory <|-- GitLabTaskFactory

    class TaskQueue {
        <<abstract>>
        +put()
        +get()
        +empty()
    }
    class InMemoryTaskQueue
    TaskQueue <|-- InMemoryTaskQueue

    class TaskHandler
    class MCPToolClient
    class GithubClient
    class GitlabClient
    class FileLock

    TaskGitHubIssue o-- MCPToolClient
    TaskGitHubIssue o-- GithubClient
    TaskGitHubPullRequest o-- MCPToolClient
    TaskGitHubPullRequest o-- GithubClient
    TaskGitLabIssue o-- MCPToolClient
    TaskGitLabIssue o-- GitlabClient
    TaskGitLabMergeRequest o-- MCPToolClient
    TaskGitLabMergeRequest o-- GitlabClient
    TaskHandler o-- Task
    InMemoryTaskQueue o-- TaskKey
    main o-- TaskGetter
    main o-- InMemoryTaskQueue
    main o-- TaskHandler
    main o-- FileLock
```

---

## 補足
- LLMクライアント群（OpenAI, LMStudio, Ollama等）はTaskHandler経由で利用される
- main.pyは全体のオーケストレーションを担う
- TaskKey/Task/TaskGetter/TaskFactory/TaskQueueは拡張性を重視し抽象クラス化


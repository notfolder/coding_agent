* `gitlab/create_file` → `{ "project_id": string, "branch": string, "file_path": string, "content": string, "commit_message": string }`
* `gitlab/update_file` → `{ "project_id": string, "branch": string, "file_path": string, "content": string, "commit_message": string }`
* `gitlab/get_file` → `{ "project_id": string, "file_path": string, "ref"?: string }`
* `gitlab/create_branch` → `{ "project_id": string, "branch": string, "ref"?: string }`
* `gitlab/search_projects` → `{ "search": string, "page"?: number, "per_page"?: number }`
* `gitlab/list_issues` → `{ "project_id": string, "labels"?: string[], "state"?: "opened" | "closed" | "all" }`
* `gitlab/create_issue` → `{ "project_id": string, "title": string, "description": string, "labels"?: string[] }`
* `gitlab/update_issue` → `{ "project_id": string, "issue_iid": number, "title"?: string, "description"?: string, "labels"?: string[] }`
* `gitlab/list_merge_requests` → `{ "project_id": string, "state"?: string, "labels"?: string[] }`
* `gitlab/create_merge_request` → `{ "project_id": string, "source_branch": string, "target_branch": string, "title": string, "description"?: string }`
* `gitlab/list_comments` → `{ "project_id": string, "issue_iid"?: number, "merge_request_iid"?: number }`
* `gitlab/create_comment` → `{ "project_id": string, "issue_iid"?: number, "merge_request_iid"?: number, "body": string }`

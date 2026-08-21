# Raw Engineering Source Data (`data/raw/`)

This directory contains synthetic raw engineering telemetry and activity records for the fictional **AcmePay Payment Service**. 

These records simulate multi-system audit logs prior to any processing, normalization, or capability extraction. In accordance with project governance rules, these raw records **do not contain normalized capability IDs, evidence bands, expertise scores, or employee rankings**.

---

## Employee Directory Reference

| Employee ID | Name | Core Role |
| :--- | :--- | :--- |
| `E001` | Rahul | Backend Engineer |
| `E002` | Amit | Backend Engineer |
| `E003` | Sneha | Platform Engineer |
| `E004` | Karan | SRE |
| `E005` | Priya | Backend Engineer |

---

## Raw Data Sources & Schemas

### 1. GitHub Repository Telemetry (`data/raw/github/`)

- **`commits.json`**: Individual git commit records containing code changes, file paths, author IDs, and branch metadata.
  - `commit_id` (string): Unique commit hash identifier.
  - `author_id` (string): Employee ID of the committer.
  - `timestamp` (ISO 8601 string): Commit timestamp.
  - `message` (string): Git commit message.
  - `files_changed` (array of strings): Repository file paths modified.
  - `lines_added` / `lines_deleted` (integer): Diff line metrics.
  - `branch` (string): Target branch name.

- **`pull_requests.json`**: Code review pull request lifecycle records.
  - `pr_id` (string): Pull request identifier.
  - `author_id` (string): Author employee ID.
  - `timestamp` (ISO 8601 string): Creation timestamp.
  - `title` / `description` (string): Functional PR summary.
  - `status` (string): `MERGED`, `OPEN`, `CLOSED`.
  - `files` (array of strings): Files included in PR diff.
  - `target_branch` (string): Merge target branch.

- **`reviews.json`**: Peer review actions performed on pull requests.
  - `review_id` (string): Review event ID.
  - `pr_id` (string): Target PR reference ID.
  - `reviewer_id` (string): Reviewer employee ID.
  - `timestamp` (ISO 8601 string): Review timestamp.
  - `state` (string): `APPROVED`, `CHANGES_REQUESTED`, `COMMENTED`.
  - `comments` (array of strings): Inline or top-level feedback comments.

- **`issues.json`**: GitHub issue tracker records for technical tasks and bugs.
  - `issue_id` (string): Issue ID.
  - `author_id` / `assignee_id` (string): Creator and assigned employee IDs.
  - `timestamp` (ISO 8601 string): Creation timestamp.
  - `title` / `description` (string): Issue details.
  - `status` (string): `OPEN`, `CLOSED`.
  - `labels` (array of strings): GitHub labels.

---

### 2. Jira Issue Tracker (`data/raw/jira/`)

- **`issues.json`**: Project management tickets, user stories, engineering tasks, and bugs.
  - `jira_id` (string): Ticket key (e.g. `PAY-101`).
  - `reporter_id` / `assignee_id` (string): Employee IDs.
  - `timestamp` / `updated_at` (ISO 8601 string): Lifecycle timestamps.
  - `issue_type` (string): `Story`, `Task`, `Bug`.
  - `summary` / `description` (string): Ticket overview.
  - `status` (string): `Done`, `In Progress`, `To Do`.
  - `components` (array of strings): System component tagging.

---

### 3. Incident Management System (`data/raw/incidents/`)

- **`incidents.json`**: Production incident logs, response team compositions, and postmortem action items.
  - `incident_id` (string): Incident tracking key (e.g. `INC-401`).
  - `reporter_id` / `lead_responder_id` (string): Incident reporter and incident commander IDs.
  - `participants` (array of strings): Responding engineers.
  - `timestamp` / `resolved_at` (ISO 8601 string): Incident start and resolution times.
  - `title` / `summary` / `root_cause` (string): Incident details.
  - `severity` (string): `SEV-1`, `SEV-2`, `SEV-3`.
  - `service` (string): Affected service identifier.
  - `action_items` (array of strings): Remediation and recovery actions.

---

### 4. Continuous Deployment System (`data/raw/deployments/`)

- **`deployments.json`**: Production and staging release deployments, blue-green cutovers, and automated rollbacks.
  - `deployment_id` (string): Deployment execution ID.
  - `deployed_by` (string): Engineer who triggered/authorized deployment.
  - `timestamp` (ISO 8601 string): Execution timestamp.
  - `environment` (string): `production` or `staging`.
  - `service` (string): Target service name.
  - `action` (string): `DEPLOY` or `ROLLBACK`.
  - `commit_hash` (string): Associated code commit hash.
  - `status` (string): `SUCCESS`, `FAILED`, `ROLLED_BACK`.
  - `notes` (string): Deployment log summary.

---

### 5. Technical Documentation (`data/raw/documentation/`)

- **`docs.json`**: Knowledge base entries, disaster recovery runbooks, architecture RFCs, and design documents.
  - `doc_id` (string): Document ID.
  - `author_id` / `last_modified_by` (string): Document author and maintainer IDs.
  - `created_at` / `updated_at` (ISO 8601 string): Creation and last update timestamps.
  - `doc_type` (string): `Runbook`, `Architecture RFC`, `Design Doc`.
  - `title` / `content_summary` (string): Content overview.
  - `service` (string): Target system/service.
  - `filepath` (string): Documentation file location.

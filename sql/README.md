# SQL scripts by environment

SQL is split by target VM so only the right scripts run per branch.

| Directory   | VM (example)        | Trigger: push to branch   | Paths that trigger workflow   |
|------------|----------------------|----------------------------|--------------------------------|
| **`feature/`** | `bioct-rag-strat-1`  | `feature/**`               | `backend/**`, `scripts/**`, **`sql/feature/**`**, workflow file |
| **`release/`** | `bioct-rag-release`  | `release/v1.0`             | `backend/**`, `scripts/**`, **`sql/release/**`**, workflow file  |

- A push to a **feature** branch that touches **`sql/feature/`** (or backend/scripts/workflow) runs the feature workflow and applies **`sql/feature/`** on the feature VM.
- A push to the **release** branch that touches **`sql/release/`** (or backend/scripts/workflow) runs the release workflow and applies **`sql/release/`** on the release VM.

**Execution order on the VM:** `init_db.sql` first, then every `migrate_*.sql` in alphabetical order. Scripts are applied on every run so new migrations are picked up.

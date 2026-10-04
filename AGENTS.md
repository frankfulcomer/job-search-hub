# Working in this repository

Codex: before planning or changing files, read the **Shared operating rules** section of [the canonical workflow instructions](/home/frank/Projects/ai-development-workflow/AGENTS.md#shared-operating-rules). The workflow-maintenance section applies only to that repository.

Codex: read `docs/development-process.md` and the requirements, architecture/ADRs, and test strategy relevant to the task.

Claude Code: follow the scoped assignment and relevant rules supplied by Codex; report missing or conflicting constraints rather than expanding scope to read external instructions.

Codex: use the runner beside the canonical instructions with the existing Job Hub profile at `/home/frank/Documents/Codex/2026-10-04/le/outputs/claude-bridge/job-hub.local.json`; its directory name reflects the historical profile location, not a second runner to maintain. If either path is unavailable, report the missing dependency rather than silently replacing the workflow.

# Collaboration instructions

- Communicate with the user in Spanish. Write repository documentation in English. The user requires visibility into every change.
- Before each block of actions, explain what will be done, why, how, and which files or settings will be affected.
- Show actual diffs inline, divided into steps, and explain each change and its validation. A link to a complete patch may supplement this explanation but never replace it.
- Distinguish prepared code, isolated validation, applied configuration, and real acceptance. Do not describe files on disk as deployed services.
- If no Git baseline exists, say so and do not invent a historical diff. Do not create commits or publish changes merely to manufacture a baseline.
- Never print secrets, credential values, or conversation content in explanations, diffs, or reports.
- Use mise for tool/environment versions, environment installation and checks, and Git hook installation. Use Task for service operations and code tests. Keep implementation in categorized scripts and architecture/operating documentation in docs/.
- Declare environment setup/validation in mise.toml; keep service deployment/operations and code tests in Taskfile.yml. Do not duplicate environment tasks in Task.
- Manage Python dependencies with uv in root pyproject.toml and uv.lock, with uv pinned by mise. Do not store Python requirements in infra/ or maintain duplicate dependency definitions.
- Keep useful descriptions/comments in TOML and substantial logic in categorized scripts/ files.
- Use lowercase document filenames under docs/ and update links/script references when renaming. Keep conventional README.md, LICENSE, and AGENTS.md filenames at the root.
- Describe the project as a local agent platform; do not frame it as a pedagogical laboratory.

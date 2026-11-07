# Repository instructions

## Start of work

1. Read `docs/PROJECT_CONTEXT.md`, `docs/TASKS.md`, `docs/DECISIONS.md`, and `docs/HANDOFF.md` before making project changes.
2. Read `docs/poc/phase0-traceability.md` for phase 0 work; use its linked report for the work package being changed.
3. Check `git status` and preserve existing user changes.

## Scope and safety

- The current objective is phase 0 POC. Keep phase 1 product implementation gated until phase 0 acceptance is recorded.
- Keep proof-of-concept evidence separate from product guarantees. Do not resolve product decisions by assumption.
- Any remote Provider request requires exact Consent and Policy approval; default to deny and retrieve credentials only from Keychain.
- Keep local model and audio evaluations offline unless the task explicitly authorizes otherwise. Do not start microphone capture without an explicit user action in the capture flow.
- Preserve the current local-first boundaries in `docs/PROJECT_CONTEXT.md`.

## Change workflow

- Keep `docs/PROJECT_CONTEXT.md`, `docs/DECISIONS.md`, `docs/TASKS.md`, `docs/HANDOFF.md`, and the phase 0 traceability matrix current when relevant.
- For code changes, run the narrow regression and the full relevant test suite when practical; record exact commands and results in the work package report.
- Before handing work back, run `git diff --check`, inspect the staged diff, and commit the completed change.
- Keep all project file operations inside `/Users/wuxiancai/Documents`.
- Communicate in Chinese unless the user requests another language.

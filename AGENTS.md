# Repository instructions

## Start of work

1. Read `docs/PROJECT_CONTEXT.md`, `docs/TASKS.md`, `docs/DECISIONS.md`, and `docs/HANDOFF.md` before making project changes.
2. Read `docs/poc/phase0-traceability.md` for phase 0 work; use its linked report for the work package being changed.
3. Check `git status` and preserve existing user changes.

## Scope and safety

- Current objective: build a usable single-user macOS beta from the validated POCs. Phase 0 evidence gaps that do not affect the beta path may be deferred; do not treat deferred evidence as passed. Record the beta scope and defer feature-specific verification until before that feature is enabled or distributed.
- Prioritize a working local-first vertical slice. Keep later capabilities behind interfaces and disabled until their own decisions, implementation, and verification are complete.
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

## 主干优先开发

- 优先推进整体框架和可用功能主线，避免因偶发模型、网络、服务商或设备现象长时间停留在局部排查。
- 小问题若不阻断整体功能、数据安全或授权边界，应记录在 `docs/TASKS.md` 或对应工作包报告的“已知问题/待回修”中，标明可复现证据、影响和回修触发条件，然后继续主线。
- 只有当问题阻断核心闭环、可能造成数据/安全风险，或无法在安全前提下继续时，才暂停主线优先处理。整体功能成形后，再集中回收非阻塞问题。
- 该规则不降低必要的安全、隐私、授权和代码回归要求；区分代码缺陷与外部偶发现象，未证实原因时记录为待判定，不先归因。

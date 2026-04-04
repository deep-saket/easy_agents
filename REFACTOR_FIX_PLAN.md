# Refactor Fix Plan

This repository is mid-migration from a MailMind-specific package layout to a shared multi-agent platform layout.

The old `src/mailmind` package has been deleted from the working tree, but many modules, tests, and package entrypoints still import from it. That leaves the repository in a partially broken state.

This file lists the fixes in the order they should be applied.

## Goal

Make the repository internally consistent and runnable again under the new platform-first layout.

## Current Status

- Fix 1: completed
- Fix 2: completed
- Fix 3: completed for source/runtime code
- Fix 4: pending decision cleanup
- Fix 5: completed
- Fix 6: structurally completed, naming cleanup still pending
- Fix 7: partially completed
- Fix 8: pending
- Fix 9: pending
- Fix 10: pending

## Fix 1: Decide the migration boundary

Before changing code, choose one of these paths:

1. Restore a thin compatibility `src/mailmind` package temporarily and migrate incrementally.
2. Finish the migration now and remove all remaining `src.mailmind.*` imports.

Recommended: finish the migration now, because the compatibility layer is already deleted and continuing half-migrated state will keep breaking imports and tests.

Selected decision for this repository:

- Finish the migration now.
- Do not restore `src/mailmind` as a compatibility package.
- Treat all remaining `src.mailmind.*` imports as migration bugs to be removed or relocated.

Status: completed

## Fix 2: Repair packaging and entrypoints

Current issue:

- [pyproject.toml](/Users/saketm10/Projects/openclaw_agents/pyproject.toml) still declares:
  - project name `mailmind`
  - script entrypoint `mailmind = "mailmind.cli.main:main"`
- The package layout now centers on `src/` plus `agents/`, not an installed `mailmind` package.

Required changes:

- Update the script entrypoint to a real current module, or remove it until a stable CLI exists.
- Re-check package discovery if concrete agents under `agents/` are meant to be importable/installable.
- Align project metadata with the new platform name if that rename is intended now.

Completed changes:

- Project name in [pyproject.toml](/Users/saketm10/Projects/openclaw_agents/pyproject.toml) was changed from `mailmind` to `easy_agent`.
- The stale `[project.scripts]` entry pointing at `mailmind.cli.main:main` was removed.

Remaining notes:

- There is still no CLI entrypoint by design.
- Package discovery still targets `src/`, which matches the current framework extraction direction.

Status: completed

## Fix 3: Remove or replace all remaining `src.mailmind` imports in shared platform code

Current issue:

Core shared modules still depend on the deleted package, so importing platform code fails.

Affected files currently include:

- [src/tools/executor.py](/Users/saketm10/Projects/openclaw_agents/src/tools/executor.py)
- [src/tools/memory_search.py](/Users/saketm10/Projects/openclaw_agents/src/tools/memory_search.py)
- [src/tools/memory_write.py](/Users/saketm10/Projects/openclaw_agents/src/tools/memory_write.py)
- [src/llm/function_gemma.py](/Users/saketm10/Projects/openclaw_agents/src/llm/function_gemma.py)
- [src/utils/time.py](/Users/saketm10/Projects/openclaw_agents/src/utils/time.py)
- [src/utils/config.py](/Users/saketm10/Projects/openclaw_agents/src/utils/config.py)
- [src/schemas/tool_io.py](/Users/saketm10/Projects/openclaw_agents/src/schemas/tool_io.py)
- [src/schemas/events.py](/Users/saketm10/Projects/openclaw_agents/src/schemas/events.py)
- [src/storage/duckdb_store.py](/Users/saketm10/Projects/openclaw_agents/src/storage/duckdb_store.py)
- [src/storage/json_store.py](/Users/saketm10/Projects/openclaw_agents/src/storage/json_store.py)
- [src/platform_logging/audit_logger.py](/Users/saketm10/Projects/openclaw_agents/src/platform_logging/audit_logger.py)

Required changes:

- Move remaining schemas/models/interfaces used by shared code into `src/schemas`, `src/storage`, `src/platform_logging`, or `src/interfaces`.
- Replace imports so shared code depends only on `src/*`, never on `src.mailmind.*`.
- If a module is still MailMind-specific, move it out of shared `src/` into `agents/mailmind/`.

Completed changes:

- Added shared framework records in [src/schemas/domain.py](/Users/saketm10/Projects/openclaw_agents/src/schemas/domain.py).
- Added shared email view schemas in [src/schemas/emails.py](/Users/saketm10/Projects/openclaw_agents/src/schemas/emails.py).
- Added shared email/repository protocols in [src/interfaces/email.py](/Users/saketm10/Projects/openclaw_agents/src/interfaces/email.py).
- Rebuilt shared config in [src/utils/config.py](/Users/saketm10/Projects/openclaw_agents/src/utils/config.py).
- Rebuilt JSONL audit storage in [src/storage/json_store.py](/Users/saketm10/Projects/openclaw_agents/src/storage/json_store.py).
- Rebuilt the DuckDB repository in [src/storage/duckdb_store.py](/Users/saketm10/Projects/openclaw_agents/src/storage/duckdb_store.py).
- Rewired shared imports in tools, schemas, logging, storage, LLM helpers, and the simple conversation agent.

Verification completed:

- `src.tools.executor` imports cleanly in the repo virtualenv.
- `src.storage.duckdb_store` imports cleanly in the repo virtualenv.
- `src.utils.config` imports cleanly in the repo virtualenv.
- `src.llm.function_gemma` imports cleanly in the repo virtualenv.
- `agents.simple_conversation.agent` imports cleanly in the repo virtualenv.
- `src.agents.graph_agent` imports cleanly in the repo virtualenv.

Remaining notes:

- Source/runtime code no longer depends on `src.mailmind.*`.
- Test files still contain many `src.mailmind.*` imports and are covered under Fix 8.

Status: completed for source/runtime code

## Fix 4: Separate generic tools from MailMind tools cleanly

Current issue:

- Generic tool infrastructure is in place under [src/tools](/Users/saketm10/Projects/openclaw_agents/src/tools).
- MailMind Gmail tools under [src/tools/gmail](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail) still depend heavily on deleted `src.mailmind.*` modules.

Required changes:

- Decide whether Gmail tools remain platform-level reusable tools or become MailMind agent tools.
- If they are MailMind-specific, move them under `agents/mailmind/tools/`.
- If they are meant to stay shared, migrate their schemas, repository protocols, and supporting models into shared `src/` modules.

Current direction:

- Gmail/email-oriented tooling has not been moved into `agents/mailmind/`.
- The current migration path is to keep these dependencies satisfied inside `src/` until a stricter framework boundary is chosen.

Remaining decision:

- Decide whether email/Gmail tooling is a first-class framework example or leftover product-specific functionality to isolate later.

Status: pending decision cleanup

## Fix 5: Repair the surviving concrete agent

Current issue:

[agents/simple_conversation/agent.py](/Users/saketm10/Projects/openclaw_agents/agents/simple_conversation/agent.py) imports `src.mailmind.config.AppSettings`, so the one visible concrete agent does not import successfully.

Required changes:

- Move the required config model into a shared config module, or define a simple agent-local config path.
- Remove the MailMind dependency from the simple conversation agent.
- Verify [endpoints/whatsapp.py](/Users/saketm10/Projects/openclaw_agents/endpoints/whatsapp.py) can construct the agent successfully.

Completed changes:

- [agents/simple_conversation/agent.py](/Users/saketm10/Projects/openclaw_agents/agents/simple_conversation/agent.py) now imports [src/utils/config.py](/Users/saketm10/Projects/openclaw_agents/src/utils/config.py) instead of `src.mailmind.config`.
- The simple conversation agent imports cleanly in the repo virtualenv.

Remaining note:

- The FastAPI endpoint/runtime path still depends on installed external packages and has not been runtime-smoke-tested end to end.

Status: completed

## Fix 6: Clean up config ownership

Current issue:

Configuration appears to still be MailMind-owned conceptually, but is being used by non-MailMind code.

Required changes:

- Decide which settings are platform-global versus MailMind-only.
- Put platform settings in shared `src/utils` or a dedicated shared config package.
- Put MailMind-only settings under `agents/mailmind/`.

Completed changes:

- Shared config ownership moved into [src/utils/config.py](/Users/saketm10/Projects/openclaw_agents/src/utils/config.py).
- Non-MailMind framework code now depends on shared config instead of `src.mailmind.config`.

Remaining cleanup:

- Some config fields are still email/Gmail/Twilio-oriented because current framework code still uses them.
- Some naming still reflects prior MailMind assumptions and should be normalized to `easy_agent` over time.

Status: structurally completed, naming cleanup still pending

## Fix 7: Restore a minimal runnable baseline

Target baseline:

- `src.agents.graph_agent` imports cleanly
- `agents.simple_conversation.agent` imports cleanly
- `endpoints.whatsapp` imports cleanly when dependencies are installed
- a small subset of platform tests passes

This baseline should be achieved before trying to restore all MailMind functionality.

Current state:

- `src.agents.graph_agent` imports cleanly in the repo virtualenv.
- `agents.simple_conversation.agent` imports cleanly in the repo virtualenv.
- Shared core modules now import cleanly in the repo virtualenv.
- End-to-end app runtime and test baseline have not yet been fully revalidated.

Status: partially completed

## Fix 8: Split tests into platform tests and MailMind tests

Current issue:

Many tests still target the deleted MailMind package.

Examples include:

- [tests/test_react_agent.py](/Users/saketm10/Projects/openclaw_agents/tests/test_react_agent.py)
- [tests/test_orchestrator.py](/Users/saketm10/Projects/openclaw_agents/tests/test_orchestrator.py)
- [tests/test_repository.py](/Users/saketm10/Projects/openclaw_agents/tests/test_repository.py)
- [tests/test_classifier.py](/Users/saketm10/Projects/openclaw_agents/tests/test_classifier.py)
- [tests/test_llm_planner.py](/Users/saketm10/Projects/openclaw_agents/tests/test_llm_planner.py)

Required changes:

- Keep platform tests that target current `src/agents`, `src/memory`, `src/interfaces`, and generic tools.
- Rewrite or relocate MailMind-specific tests so they match the new agent package layout.
- Remove stale tests only if their covered functionality no longer exists.

Current state:

- Test files still contain many `src.mailmind.*` imports.
- This is now the main remaining import-migration surface.

Status: pending

## Fix 9: Rebuild MailMind in its new location or remove stale references

Current issue:

The repo still documents MailMind as the first concrete agent, but the implementation has been removed from `src/mailmind` and not fully re-established under `agents/mailmind/`.

Required changes:

- Either rebuild the MailMind runtime under `agents/mailmind/` using the shared graph platform,
- or remove stale docs, imports, and tests until that agent exists again.

Current state:

- No rebuild is in progress.
- Stale references remain mostly in tests and docs.

Status: pending

## Fix 10: Update documentation after code is stable

Required changes:

- Update [README.md](/Users/saketm10/Projects/openclaw_agents/README.md) to match the actual runnable structure.
- Document which agents are real versus placeholders.
- Document current entrypoints and test commands.

Status: pending

## Recommended execution order

1. Finish Fix 7 by validating a minimal runnable baseline.
2. Execute Fix 8 by migrating or pruning tests that still import `src.mailmind.*`.
3. Decide Fix 4 and Fix 9 together: keep email tooling/framework examples in `src/` or isolate/remove stale MailMind-specific behavior.
4. Update documentation last.

## Notes on risk

- The biggest risk is mixing platform code and MailMind code again instead of drawing a clean boundary.
- The second biggest risk is trying to make all tests pass before deciding whether MailMind is still part of the active runtime.
- The fastest safe path is to first restore a clean platform baseline, then reintroduce MailMind intentionally.

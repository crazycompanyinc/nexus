# Changelog

All notable changes to the Nexus project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adates to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `CHANGELOG.md` — project changelog for tracking changes.
- Plugin builtins: AWS, Database, Docker, Email, Filesystem, GitHub, HTTP, Jira, Kubernetes, Slack — each with inline stubs, docstrings, and type annotations.
- `NexusStore.health_check()` — health monitoring endpoint with memory usage approximation.
- `NexusStore.search_calls()` — multi-criteria call search with duration filtering.
- CLI: `npx nexus demo` — full demo workflow (install plugins, register agents, grant permissions, call tools, run workflow).
- `StepResult.to_dict()` — JSON-serializable dict conversion for pipeline step results.
- `__bool__` on `StepResult` — truthy check based on `success` field.
- `__len__` on `WorkflowBuilder` — count of stored workflows.

### Changed
- CLI: All command functions now have full docstrings.
- Plugin builtins: Improved from stub functions to full `BasePlugin` subclasses with `execute()` methods.

### Fixed
- `WorkflowBuilder.__repr__` — now returns correct format with workflow count.
- `StepResult.__repr__` — now returns step index, tool, action, status, and duration.

## [1.6.0] — 2026-05-26

### Added
- `ErrorResponse` now includes `request_id` and `timestamp` fields for full traceability across all error handlers.
- `body_size_limit_middleware` — rejects request bodies exceeding configurable limit (default 1 MB) with HTTP 413, protecting against large payload attacks.
- `create_app(max_body_size=...)` parameter — configurable request body size limit.

### Changed
- Version bumped from 1.5.0 → 1.6.0.
- All exception handlers (PermissionError, KeyError, ValueError, global) now populate `request_id` and `timestamp` in error responses.
- Added `datetime` import to server module for error response timestamps.

### Security
- Request body size validation on POST/PATCH/PUT methods prevents resource exhaustion from oversized payloads.

## [1.2.0] — 2026-05-23

### Added
- `NexusStore.import_()` / `export()` — full store serialization round-trip with ISO 8601 datetime parsing.
- `Pipeline._resolve_params()` — `$previous`, `$all`, `$step{N}` parameter reference resolution.
- Conditional step execution in `Pipeline.run()` — `previous_failed` / `previous_succeeded` conditions.
- `WorkflowBuilder.patch()` — PATCH semantics for partial workflow updates.
- `RateLimitMiddleware` — in-memory sliding window rate limiter with stale IP cleanup.
- `PaginatedResponse` / `ErrorResponse` — standard API response envelopes.
- `NexusSelfEvaluator` — automated code quality evaluation with 15+ checks.
- `Continual Harness` integration — self-improving agent system based on arXiv:2605.09998v1.

### Changed
- `NexusStore.agent_calls()` now iterates in reverse chronological order with optional status filter and limit.
- `NexusStore.stats()` replaced by `snapshot()` for full store state capture.

## [1.0.0] — 2026-05-20

### Initial Release
- Core: `NexusStore`, `UnifiedToolAPI`, `AccessControl`, `UsageMetrics`.
- Plugins: `PluginManager`, `PluginRegistry`, `PluginLoader`, `BasePlugin` SDK.
- Server: FastAPI with rate limiting, CORS, error handlers, OpenAPI docs.
- CLI: Click-based CLI with init, register, install, bind, call, workflow, serve commands.
- Workflow: `WorkflowBuilder`, `Pipeline`, `StepResult`, conditional execution, retry with backoff.
- Permissions: `AccessControl` with read/write/admin levels, audit trail.
- Composition: Workflow composition with parameter resolution and fallback chains.

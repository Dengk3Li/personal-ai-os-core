# Personal AI OS v0.8 Development Taskbook

## Objective

Turn a dependency graph into a bounded operating loop: recover persisted truth, dispatch every task that is currently safe, show real execution, and stop exactly where human authority or runtime recovery is required.

The release also establishes a minimal domain-context contract for the future Secretary entrance. The system selects one primary domain and passes references, not a full personal archive.

## Delivered slice

### Bounded auto advance

`AutoAdvanceEngine` scans SQLite task truth in stable insertion order. A task is selectable only when it is `QUEUED`, every dependency is `DONE` or `ARCHIVED`, and it has no pending decision. The existing Broker remains the final authority for Human Gates, Adapter availability, atomic claim, run creation, artifact registration, and review transition.

Each invocation has a 1–100 step limit and a 1–20 failure budget. It processes multiple independent ready branches in stable sequence; their join remains queued until accepted upstream results close the dependency. SQLite claim prevents duplicate model calls, while competing advance requests may both record their selection attempts and outcomes. Adapter and runtime failures make the whole receipt fail and stop when the failure budget is reached.

The engine never performs these actions:

- accept a result in `REVIEW`;
- choose or approve a Human Gate;
- resume `BLOCKED` or `PAUSED` work;
- re-dispatch `IN_PROGRESS` work after interruption;
- publish, merge, push, or promote memory.

### Single pending Human Gate

Human Gate creation now uses an immediate SQLite transaction. Competing runtime instances either create or read the same pending decision before any Adapter call. Resolution remains a separate explicit human action.

### Domain Context compiler

`compile_domain_context()` accepts a domain registry and emits `personal-ai-os.domain-context/v1`. Only these layers are recognized, in this order:

1. `domain_contract`
2. `active_project`
3. `current_state`
4. `relevant_knowledge`
5. `historical_decisions`
6. `constraints`
7. `excluded_context`

The result contains references, a static domain processing style in `persona`, and allowed tool identifiers. `persona` is not a user identity or long-term personal memory. Missing or duplicate domains return `UNKNOWN`; unknown layers and invalid reference lists return `BLOCKED`. A real registry may contain private references and therefore belongs in a local ignored path, not public Git or browser projection.

### Workbench operation

The Work Progress page exposes a runtime-only auto-advance control scoped to the selected workflow. It uses the configured model and an available Adapter, polls the persisted projection while the request is active, and reports the number of dispatched tasks plus the stop reason. Static showcase mode does not expose the control. CLI callers can explicitly omit workflow scope for a global drain.

## Real-use acceptance

1. Register an actual local work plan under an ignored `.personal-ai-os/` path.
2. Confirm browser projection contains task structure but no local paths or server-only context.
3. Advance a synthetic parallel branch and verify both tasks stop in `REVIEW` while their join remains queued.
4. Advance a Human Gate from two runtime instances and verify one pending decision and zero model calls.
5. Restart with an `IN_PROGRESS` task and verify it remains a recovery boundary.
6. Run full Python and Workbench suites, browser interaction, privacy scan, and Git diff checks.

## Next delivery lines

- Adapter status reconciliation for interrupted external runs;
- cancellable or streaming execution transport;
- workspace registry with path-free browser projection;
- domain discovery from natural-language intent;
- model route selection from capability, context, privacy, and availability;
- repository-development preset with verified Git closure;
- nested module scanner with evidence-linked graph claims.

## Release boundary

This version proves bounded automatic dispatch, not unattended autonomous development. A configured Adapter is required for model execution. Existing `IN_PROGRESS` tasks remain recovery gates because the current synchronous Adapter cannot reconcile an external request after a process crash. Public fixtures, docs, and tests contain only generic profiles and synthetic work.

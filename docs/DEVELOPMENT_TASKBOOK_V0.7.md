# Personal AI OS v0.7 Development Taskbook

## Objective

Use Personal AI OS to govern development of its own public core, then test whether the LongTask loop reduces repeated context reconstruction, missed handoffs, and unverifiable completion in real repository work.

The release is an MVP of the operating layer, not a claim of autonomous software development. It must preserve human authority over scope, external writes, result acceptance, and Git closure.

## Delivered slice

### Versioned local plan sync

`personal-ai-os.runtime-plan/v1` defines workflows and dependency-ordered tasks. `runtime sync-plan` validates the complete plan before writing, creates missing records, and leaves all existing runtime truth unchanged.

Actual project plans belong under `.personal-ai-os/` or another ignored local path. Public fixtures and screenshots contain structure only.

Task `context` remains server-side recovery metadata and is omitted from the browser projection. Model-bound instructions must be placed explicitly under `context.model_context`; this payload is capped at 12,000 characters.

### Live model-call state

The Broker now creates a local run and atomically moves a task to `IN_PROGRESS` before calling the Adapter. The Workbench polls the runtime while the request is pending. Success records the external run identity, artifact, and review transition; failure records a rejected run and blocked task.

This establishes a real working-state signal. It does not yet provide streaming tokens, cancellation, background job recovery, or remote process control.

### Optional working pet

The Workbench offers three choices: Blue Whale Maid, model animal, and off. Six final GIF variants are lazy-loaded only for running tasks. Activity and mood selection is deterministic for a task, and reduced-motion users receive a static fallback.

The asset pack has its own manifest and notice. Reference images, prompts, intermediate files, and private materials are excluded.

## Next delivery lines

### 1. Local workspace registry

- Register exact workspace identities through CLI only.
- Keep absolute paths in SQLite and omit them from browser projections.
- Record additive Git observations with timestamp, branch, HEAD, dirty count, and `CLEAN / DIRTY / UNKNOWN`.
- Treat timeouts and FileProvider uncertainty as `UNKNOWN`.
- Bind a workflow to registered workspace IDs without copying source content into task context.

Acceptance: one repository and one linked worktree can be refreshed without writes, path disclosure, hydration, or state guessing.

### 2. Repository-development preset

- Inspect current workspace truth.
- Confirm scope and ownership of existing dirty changes.
- Execute one bounded implementation task.
- Run proportionate verification.
- Request human acceptance.
- Record a fresh Git closure.

Acceptance: the public core completes one feature through its own task system, and restart recovery does not require rereading the whole conversation.

### 3. Cross-executor recovery

- Add an Adapter contract for Codex or another local coding executor.
- Run one task with two executors across an intentional interruption.
- Pass only accepted upstream artifacts, task-local context, and bounded repository evidence.
- Keep credentials, local paths, and unrelated memory outside model context.

Acceptance: the second executor continues the same task identity and produces an inspectable result without duplicating the first executor's finished work.

### 4. Workspace-to-module graph

- Freeze the module manifest fields for input, output, capability, dependency, layer, and nested subgraph.
- Add a read-only scanner for code, configuration, and public interfaces.
- Produce directed edges, missing-capability nodes, connected components, cycles, and abstraction layers.
- Preserve user layout and annotations separately from scan evidence.
- Convert a confirmed annotation into a task candidate.

Acceptance: a previously unseen small program produces a navigable dependency graph whose claims link back to files or manifests.

### 5. Secretary and domain routing

- Interpret a natural-language goal into domain, output form, and bounded workline.
- Load only the selected domain persona, accepted memory references, and required tools.
- Compress blockers into reason, evidence, impact, choices, and a suggested action.
- Observe stale work in shadow mode before enabling notifications.

Acceptance: two domains recover independently without carrying each other's context, and reminders never change task state.

### 6. Workflow presets and model choice

- Validate the five-Agent science loop with alternative experiment paths.
- Validate a short source-to-draft document chain.
- Validate a deep evidence-pool-to-structured-report chain.
- Let each node select a compatible model or executor and preserve that assignment in the run.

Acceptance: parallel branches, repeated attempts, Human Gates, and downstream artifact handoff are visible from one task truth source.

### 7. Product-value trial

Run a repository task from intake through decomposition, assignment, interruption, decision, recovery, review, and Git closure. Record:

- time required for a new executor to recover context;
- number of duplicated tasks or repeated investigations;
- time spent waiting for human decisions;
- review rework count;
- number of completion claims rejected for missing evidence.

The MVP is useful only if these measures improve relative to the current conversation-by-conversation workflow.

## Release gates

1. Public diff contains no private paths, credentials, business-specific abbreviations, task bodies, or run receipts.
2. Local plan and SQLite remain ignored by Git.
3. Python, Workbench, API, browser interaction, asset decoding, reduced-motion fallback, and Git diff checks pass.
4. A real slow Adapter shows `IN_PROGRESS` and a working pet before its response completes.
5. Two competing runtime instances call the model once for the same queued task.
6. Documentation distinguishes delivered runtime behavior, synthetic demonstration, and planned capability.
7. Final push and main promotion remain explicit human release actions.

# Execution ownership contract

`personal-ai-os.single-owner-progression/v1` is a pure, storage-agnostic
contract for bounded execution. It is suitable for a local worker, a browser
service, or another adapter that already has an authoritative state store.

The contract separates policy decisions from side effects:

- `select_ready_task` chooses one queued task only when an upstream policy has
  explicitly marked it `READY` and `may_dispatch`.
- `claim_owner` creates one owner and one lease. `revision` is the compare and
  swap token; stale writers fail with `STALE_STATE`.
- `enqueue_trigger` merges repeated requests by `dedupe_key`, preserving all
  trigger IDs without creating a second dispatch.
- `authorize_step` records a pre-side-effect checkpoint and enforces step and
  token budgets before execution.
- Lease expiry, uncertain side effects, and explicit human stops become
  recovery or resume boundaries. They never replay work implicitly.
- `submit_for_review` closes execution at `WAITING_REVIEW`; acceptance remains
  an external human action.

The module returns new JSON-compatible snapshots and performs no process
launch, model call, database write, or automatic review acceptance. A caller
must persist each returned snapshot atomically under its expected revision.

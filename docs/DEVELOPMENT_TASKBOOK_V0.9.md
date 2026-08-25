# Personal AI OS v0.9 Development Taskbook

## Objective

Choose a compatible execution route for each ready task without weakening the bounded auto-advance, Human Gate, or single-claim guarantees established in v0.8.

## Delivered slice

### Versioned runtime route catalog

`personal-ai-os.runtime-routes/v1` declares route ID, tier, capabilities, context limit, Adapter ID, model ID, and enabled state. Unknown fields are rejected so credentials cannot be embedded in the catalog. API keys and endpoint URLs remain process-local configuration.

### Per-task selection

Auto advance evaluates each task independently. It chooses the smallest available route that meets the task tier, required capabilities, and `context.routing.estimated_context_tokens`. A requested route remains subject to the same requirements.

Human Gates are resolved before route availability. Route failure happens before claim and consumes the bounded failure budget. A successful model response still stops at `REVIEW`.

### Atomic route evidence

Adapter availability is sampled once per Adapter for each dispatch. Task claim, local run creation, and the selected-route event share one SQLite transaction. The route event carries the real run ID; a competing process that loses the claim records no selected route and does not call the model.

## Entrances

```bash
personal-ai-os runtime advance \
  --store .personal-ai-os/runtime.db \
  --routes examples/runtime-routes.json \
  --workflow science

personal-ai-os runtime serve \
  --store .personal-ai-os/runtime.db \
  --routes examples/runtime-routes.json
```

The local API accepts `route_mode=automatic` and an optional `requested_route`; it always uses the server-owned catalog. When a server has routes but no fixed default model, the existing Work Progress action uses automatic routing.

## Acceptance

1. Two routes sharing one Adapter produce one availability probe per dispatch.
2. Competing runtime instances produce one model call and one selected-route event bound to its run.
3. The losing instance returns no route binding.
4. Human Gate tasks create a decision before route availability is checked.
5. Client payloads cannot inject a replacement route catalog.
6. Fixed Adapter and model execution remains available.

## Release boundary

This version adds bounded route selection, not background scheduling or model discovery. Streaming, cancellation, external-run reconciliation, multi-machine leases, Token Manager, and a visual route editor remain outside this slice.

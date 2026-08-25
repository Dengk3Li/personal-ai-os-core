# Execution settings read contract

`GET /api/settings/execution` is the read-only settings projection for the
Workbench. It reports whether the saved execution policy can run a task without
moving, creating, or rewriting any runtime state.

The response uses the versioned envelope
`personal-ai-os.execution-settings/v1`:

```json
{
  "schema_version": "personal-ai-os.execution-settings/v1",
  "status": "READY",
  "data_source": "runtime",
  "execution": {
    "task_dispatch_ready": true,
    "advance_route_mode": "fixed",
    "advance_ready": true
  },
  "execution_settings": {},
  "adapters": [],
  "default_model": ""
}
```

`execution_settings` contains the saved route mode and route metadata. Adapter
availability is exposed separately in `adapters`; credential values, API keys,
endpoint secrets, and protocol diagnostics are never part of this projection.
In `public-safe` mode, model, adapter, route, and capability identifiers are
stable public aliases and project bindings are omitted.

The task page consumes only readiness and task state. Model, route, adapter, API
and Codex project configuration remains in the top-right Settings surface.
`POST /api/settings/execution` is the mutation endpoint and is accepted only by
the `private-local` projection; a GET request never changes the SQLite store.

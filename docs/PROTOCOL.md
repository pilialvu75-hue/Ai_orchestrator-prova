# AIrLab HTTP protocol v0.1

## GET /health

Returns service and engine readiness.

## GET /v1/capabilities

Returns the active engine capability snapshot. Clients must feature-detect rather than assume local hardware exists.

## POST /v1/tasks

Request:

```json
{
  "task": "Create a simple notes application",
  "project_id": "demo",
  "target": "web",
  "mode": "plan",
  "context": {}
}
```

`mode` is one of `plan`, `implement`, or `repair`.

Response contains a request id, engine id, deterministic plan, optional file operations and non-sensitive metadata.

## Authentication

No token is required on the default loopback-only listener. If AIrLab is exposed beyond loopback, startup fails unless `AIRLAB_AUTH_TOKEN` is configured. The API then requires `Authorization: Bearer <token>`.

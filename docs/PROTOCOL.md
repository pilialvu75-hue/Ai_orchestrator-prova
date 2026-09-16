# AIrLab HTTP protocol v0.2

## GET /health

Returns service and engine readiness.

## GET /v1/capabilities

Returns the active engine capability snapshot. Clients must feature-detect rather than assume local hardware exists. The snapshot now advertises task families, accepted input kinds and artifact formats.

## POST /v1/tasks

Minimal software request:

```json
{
  "task": "Create a simple notes application"
}
```

CAD reconstruction request:

```json
{
  "task": "Reconstruct this broken bracket",
  "project_id": "bracket-001",
  "task_family": "cad",
  "task_kind": "cad.reconstruct",
  "mode": "plan",
  "inputs": [
    {"kind": "image", "reference": "attachment:front"},
    {"kind": "measurement", "reference": "hole_spacing=63mm"}
  ],
  "requested_artifacts": ["step", "stl", "3mf"],
  "context": {}
}
```

Printer-specific G-code is a separate manufacturing task and requires a printer profile:

```json
{
  "task": "Slice the validated model",
  "task_family": "manufacturing",
  "task_kind": "manufacturing.slice",
  "requested_artifacts": ["gcode"],
  "context": {"printer_profile": "printer:demo"}
}
```

`mode` is one of `plan`, `implement`, or `repair`.

The response contains a request id, engine id, deterministic plan, optional file operations, planned/generated artifact descriptors and non-sensitive metadata.

## Authentication

No token is required on the default loopback-only listener. If AIrLab is exposed beyond loopback, startup fails unless `AIRLAB_AUTH_TOKEN` is configured. The API then requires `Authorization: Bearer <token>`.

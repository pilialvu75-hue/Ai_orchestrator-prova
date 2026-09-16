# AIrLab task families

AIrLab is a platform first. A task family is a specialist capability added on top of the same API, routing, Library, Researcher and Diagnostics foundation.

## Initial catalog

- `software.*`: applications and general software projects.
- `web.*`: websites and web applications.
- `cad.*`: parametric 3D/CAD reconstruction, modelling, revision and export.
- `manufacturing.*`: manufacturability validation and printer-specific slicing.

The catalog is intentionally small. New task families are added only after their contracts, tools and validators are defined.

## Generic inputs

A task may reference text, images, drawings, files, measurements or an existing project. Binary assets are not embedded in the task JSON; clients pass a reference that an adapter can resolve later.

This allows a future CAD request to start from a photo, sketch or drawing without coupling the core protocol to one storage system.

## CAD source-of-truth rule

For `cad.*`, AIrLab must preserve an editable/parametric master before producing derived print files. STL is never the canonical project source.

A future project may therefore produce:

```text
project/
  project.airlab.json      source metadata / parameters
editable/
  model.step               neutral editable exchange
  model.scad               optional parametric source
  sketch.dxf               optional 2D sketch
printable/
  model.3mf
  model.stl
manufacturing/
  printer-profile.json
output/
  model.gcode              printer/profile-specific derivative
```

## G-code safety boundary

`gcode` belongs to `manufacturing.*`, not `cad.*`. A request for G-code must include an explicit printer profile. This prevents AIrLab from treating a generic 3D model as safe machine instructions.

The future slicer adapter, not an LLM, will be responsible for converting a validated model plus printer/material profile into machine-specific G-code.

## Planned growth

The platform can later add further families without changing Cantiere's transport contract, for example electronics, documents, automation or media workflows.

from __future__ import annotations

TASK_CATALOG: dict[str, tuple[str, ...]] = {
    "software": ("software.build", "software.repair", "software.review"),
    "web": ("web.build", "web.repair", "web.review"),
    "cad": ("cad.reconstruct", "cad.model", "cad.revise", "cad.export"),
    "manufacturing": ("manufacturing.validate", "manufacturing.slice"),
}

DEFAULT_TASK_KIND: dict[str, str] = {
    "software": "software.build",
    "web": "web.build",
    "cad": "cad.model",
    "manufacturing": "manufacturing.validate",
}


def default_task_kind(family: str) -> str:
    try:
        return DEFAULT_TASK_KIND[family]
    except KeyError as exc:
        raise ValueError("unsupported task_family") from exc


def validate_task_kind(family: str, task_kind: str) -> None:
    if task_kind not in TASK_CATALOG.get(family, ()):
        allowed = ", ".join(TASK_CATALOG.get(family, ()))
        raise ValueError(f"unsupported task_kind for {family}; allowed: {allowed}")

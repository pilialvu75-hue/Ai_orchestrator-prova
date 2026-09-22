from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Iterable

from .model import ResourceDescriptor, ResourceHealth, ResourceRegistry


class CandidateStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    VERIFYING = "VERIFYING"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    DEPRECATED = "DEPRECATED"


class VerificationCheck(StrEnum):
    DOCUMENTATION = "documentation"
    TERMS = "terms"
    QUOTA = "quota"
    CAPABILITY = "capability"
    FALLBACK = "fallback"


_REQUIRED_CHECKS = frozenset(
    {
        VerificationCheck.DOCUMENTATION,
        VerificationCheck.TERMS,
        VerificationCheck.QUOTA,
        VerificationCheck.CAPABILITY,
        VerificationCheck.FALLBACK,
    }
)


@dataclass(frozen=True)
class VerificationEvidence:
    check: VerificationCheck
    source: str
    checked_at: str
    note: str = ""

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("verification source is required")
        if not self.checked_at.strip():
            raise ValueError("checked_at is required")


@dataclass(frozen=True)
class ResourceCandidate:
    candidate_id: str
    draft: ResourceDescriptor
    discovered_at: str
    discovered_by: str
    status: CandidateStatus = CandidateStatus.DISCOVERED
    evidence: tuple[VerificationEvidence, ...] = ()
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id is required")
        if not self.discovered_at.strip():
            raise ValueError("discovered_at is required")
        if not self.discovered_by.strip():
            raise ValueError("discovered_by is required")
        if self.status is CandidateStatus.REJECTED and not self.rejection_reason:
            raise ValueError("rejected candidate requires rejection_reason")

    @property
    def completed_checks(self) -> frozenset[VerificationCheck]:
        return frozenset(item.check for item in self.evidence)

    @property
    def missing_checks(self) -> frozenset[VerificationCheck]:
        return _REQUIRED_CHECKS.difference(self.completed_checks)

    @property
    def promotable(self) -> bool:
        return (
            self.status is CandidateStatus.VALIDATED
            and not self.missing_checks
            and self.draft.health is ResourceHealth.UNKNOWN
        )


class ResourceCandidateRegistry:
    """Validation gate between Researcher discovery and official registry."""

    def __init__(self, candidates: Iterable[ResourceCandidate] = ()) -> None:
        self._candidates: dict[str, ResourceCandidate] = {}
        for candidate in candidates:
            self.submit(candidate)

    def submit(self, candidate: ResourceCandidate) -> None:
        if candidate.candidate_id in self._candidates:
            raise ValueError(f"duplicate candidate_id: {candidate.candidate_id}")
        if candidate.status is not CandidateStatus.DISCOVERED:
            raise ValueError("new candidates must start DISCOVERED")
        self._candidates[candidate.candidate_id] = candidate

    def get(self, candidate_id: str) -> ResourceCandidate | None:
        return self._candidates.get(candidate_id)

    def all(self) -> tuple[ResourceCandidate, ...]:
        return tuple(self._candidates.values())

    def add_evidence(
        self,
        candidate_id: str,
        evidence: VerificationEvidence,
    ) -> ResourceCandidate:
        candidate = self._require_mutable(candidate_id)
        deduped = tuple(
            item for item in candidate.evidence if item.check is not evidence.check
        ) + (evidence,)
        updated = replace(
            candidate,
            status=CandidateStatus.VERIFYING,
            evidence=deduped,
        )
        self._candidates[candidate_id] = updated
        return updated

    def validate(self, candidate_id: str) -> ResourceCandidate:
        candidate = self._require_mutable(candidate_id)
        missing = candidate.missing_checks
        if missing:
            raise ValueError(
                "candidate cannot be validated; missing checks: "
                + ", ".join(sorted(check.value for check in missing))
            )
        updated = replace(candidate, status=CandidateStatus.VALIDATED)
        self._candidates[candidate_id] = updated
        return updated

    def reject(self, candidate_id: str, reason: str) -> ResourceCandidate:
        candidate = self._require_mutable(candidate_id)
        cleaned = reason.strip()
        if not cleaned:
            raise ValueError("rejection reason is required")
        updated = replace(
            candidate,
            status=CandidateStatus.REJECTED,
            rejection_reason=cleaned,
        )
        self._candidates[candidate_id] = updated
        return updated

    def deprecate(self, candidate_id: str) -> ResourceCandidate:
        candidate = self._candidates[candidate_id]
        updated = replace(candidate, status=CandidateStatus.DEPRECATED)
        self._candidates[candidate_id] = updated
        return updated

    def promote(
        self,
        candidate_id: str,
        official_registry: ResourceRegistry,
    ) -> ResourceDescriptor:
        candidate = self._candidates[candidate_id]
        if not candidate.promotable:
            raise ValueError("candidate is not validated/promotable")
        if official_registry.get(candidate.draft.resource_id) is not None:
            raise ValueError(
                f"resource already exists: {candidate.draft.resource_id}"
            )
        official_registry.register(candidate.draft)
        return candidate.draft

    def _require_mutable(self, candidate_id: str) -> ResourceCandidate:
        candidate = self._candidates[candidate_id]
        if candidate.status in {
            CandidateStatus.REJECTED,
            CandidateStatus.DEPRECATED,
            CandidateStatus.VALIDATED,
        }:
            raise ValueError(
                f"candidate is terminal: {candidate.status.value}"
            )
        return candidate

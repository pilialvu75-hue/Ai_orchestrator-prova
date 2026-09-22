import unittest

from airlab.resources import (
    CandidateStatus,
    ResourceCandidate,
    ResourceCandidateRegistry,
    ResourceDescriptor,
    ResourceHealth,
    ResourceRegistry,
    UsageClass,
    VerificationCheck,
    VerificationEvidence,
)


def _draft(resource_id: str = "new-provider") -> ResourceDescriptor:
    return ResourceDescriptor(
        resource_id=resource_id,
        provider="New Provider",
        capabilities=("llm.coding",),
        free_tier=True,
        health=ResourceHealth.UNKNOWN,
        replacement_candidates=("openrouter_free_pool",),
        usage_classes=(UsageClass.DEVELOPMENT,),
        documentation_urls=("https://example.invalid/docs",),
        terms_urls=("https://example.invalid/terms",),
    )


def _candidate() -> ResourceCandidate:
    return ResourceCandidate(
        candidate_id="candidate-1",
        draft=_draft(),
        discovered_at="2026-09-22T10:00:00Z",
        discovered_by="researcher",
    )


def _evidence(check: VerificationCheck) -> VerificationEvidence:
    return VerificationEvidence(
        check=check,
        source=f"https://example.invalid/{check.value}",
        checked_at="2026-09-22T10:05:00Z",
    )


class ResourceCandidateTests(unittest.TestCase):
    def test_new_candidate_starts_discovered_and_not_promotable(self) -> None:
        candidate = _candidate()
        self.assertEqual(candidate.status, CandidateStatus.DISCOVERED)
        self.assertFalse(candidate.promotable)
        self.assertEqual(len(candidate.missing_checks), 5)

    def test_validation_fails_until_all_required_checks_exist(self) -> None:
        registry = ResourceCandidateRegistry([_candidate()])
        registry.add_evidence(
            "candidate-1",
            _evidence(VerificationCheck.DOCUMENTATION),
        )
        with self.assertRaises(ValueError):
            registry.validate("candidate-1")

    def test_full_evidence_can_validate_and_promote_once(self) -> None:
        candidates = ResourceCandidateRegistry([_candidate()])
        for check in VerificationCheck:
            candidates.add_evidence("candidate-1", _evidence(check))

        validated = candidates.validate("candidate-1")
        self.assertTrue(validated.promotable)

        official = ResourceRegistry()
        promoted = candidates.promote("candidate-1", official)
        self.assertEqual(promoted.resource_id, "new-provider")
        self.assertIs(official.get("new-provider"), promoted)

        with self.assertRaises(ValueError):
            candidates.promote("candidate-1", official)

    def test_evidence_for_same_check_is_replaced_not_duplicated(self) -> None:
        candidates = ResourceCandidateRegistry([_candidate()])
        candidates.add_evidence(
            "candidate-1",
            _evidence(VerificationCheck.TERMS),
        )
        candidates.add_evidence(
            "candidate-1",
            VerificationEvidence(
                check=VerificationCheck.TERMS,
                source="https://example.invalid/new-terms",
                checked_at="2026-09-22T10:10:00Z",
            ),
        )
        candidate = candidates.get("candidate-1")
        self.assertEqual(len(candidate.evidence), 1)
        self.assertEqual(
            candidate.evidence[0].source,
            "https://example.invalid/new-terms",
        )

    def test_rejected_candidate_cannot_receive_more_evidence(self) -> None:
        candidates = ResourceCandidateRegistry([_candidate()])
        rejected = candidates.reject("candidate-1", "terms prohibit intended use")
        self.assertEqual(rejected.status, CandidateStatus.REJECTED)
        with self.assertRaises(ValueError):
            candidates.add_evidence(
                "candidate-1",
                _evidence(VerificationCheck.DOCUMENTATION),
            )

    def test_live_health_claim_cannot_be_promoted_from_research_evidence(self) -> None:
        unsafe = ResourceCandidate(
            candidate_id="candidate-live",
            draft=ResourceDescriptor(
                resource_id="unsafe",
                provider="Unsafe Provider",
                capabilities=("llm.coding",),
                free_tier=True,
                health=ResourceHealth.HEALTHY,
            ),
            discovered_at="2026-09-22T10:00:00Z",
            discovered_by="researcher",
        )
        candidates = ResourceCandidateRegistry([unsafe])
        for check in VerificationCheck:
            candidates.add_evidence("candidate-live", _evidence(check))
        validated = candidates.validate("candidate-live")
        self.assertFalse(validated.promotable)
        with self.assertRaises(ValueError):
            candidates.promote("candidate-live", ResourceRegistry())


if __name__ == "__main__":
    unittest.main()

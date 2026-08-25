"""Tests for the public single-owner bounded progression contract."""

from __future__ import annotations

import unittest

import personal_ai_os.single_owner_progression as sop


def make_state(**policy):
    return sop.create_execution_state(
        task_id="task-example",
        policy={"max_steps": 2, "max_tokens": 100, "failure_budget": 1, **policy},
    )


def claim(state, **kwargs):
    return sop.claim_owner(
        state,
        owner_id=kwargs.get("owner_id", "worker-a"),
        claim_id=kwargs.get("claim_id", "claim-1"),
        claimed_at=kwargs.get("claimed_at", "2026-08-26T01:00:00Z"),
        lease_expires_at=kwargs.get("lease_expires_at", "2026-08-26T01:15:00Z"),
    )


class SingleOwnerProgressionTests(unittest.TestCase):
    def test_ready_selection_is_deterministic_and_excludes_non_ready_decisions(self):
        selected = sop.select_ready_task(
            [
                {"task_id": "task-2", "seq": 2, "status": "QUEUED"},
                {"task_id": "task-1", "seq": 1, "status": "QUEUED"},
                {"task_id": "task-0", "seq": 0, "status": "QUEUED"},
            ],
            {
                "task-0": {"disposition": "WAITING_REVIEW", "may_dispatch": False},
                "task-1": {"disposition": "READY", "may_dispatch": True},
                "task-2": {"disposition": "READY", "may_dispatch": True},
            },
        )

        self.assertEqual("task-1", selected["task"]["task_id"])
        self.assertEqual("READY", selected["disposition"])
        self.assertTrue(selected["may_dispatch"])

    def test_claim_is_single_owner_and_uses_revision_cas(self):
        state = claim(make_state())

        self.assertEqual("CLAIMED", state["status"])
        self.assertEqual("worker-a", state["owner"]["owner_id"])
        self.assertEqual(1, state["revision"])
        with self.assertRaises(sop.ContractViolation) as caught:
            claim(state, owner_id="worker-b", claim_id="claim-2")
        self.assertEqual("OWNER_ALREADY_CLAIMED", caught.exception.code)

        with self.assertRaises(sop.ContractViolation) as caught:
            sop.renew_lease(
                state,
                owner_id="worker-b",
                claim_id="claim-2",
                lease_expires_at="2026-08-26T01:20:00Z",
                expected_revision=0,
            )
        self.assertEqual("STALE_STATE", caught.exception.code)

    def test_duplicate_trigger_merges_without_a_second_dispatch(self):
        state = make_state()
        first = sop.enqueue_trigger(
            state,
            trigger_id="trigger-1",
            dedupe_key="task:example",
            source="request",
            requested_at="2026-08-26T01:00:00Z",
        )
        state = claim(first["state"])
        second = sop.enqueue_trigger(
            state,
            trigger_id="trigger-2",
            dedupe_key="task:example",
            source="retry",
            requested_at="2026-08-26T01:01:00Z",
        )

        self.assertEqual("MERGED", second["disposition"])
        self.assertEqual(1, len(second["state"]["triggers"]))
        self.assertEqual(2, second["state"]["triggers"][0]["merged_count"])
        self.assertEqual(
            ["trigger-1", "trigger-2"],
            second["state"]["triggers"][0]["trigger_ids"],
        )
        self.assertEqual("CLAIMED", second["state"]["status"])

    def test_expired_lease_enters_recovery_instead_of_being_taken_over(self):
        recovered = sop.expire_lease(
            claim(make_state()), observed_at="2026-08-26T01:16:00Z"
        )
        self.assertEqual("RECOVERY_REQUIRED", recovered["status"])
        self.assertEqual("LEASE_EXPIRED", recovered["stop_reason"])
        with self.assertRaises(sop.ContractViolation) as caught:
            claim(recovered, owner_id="worker-b", claim_id="claim-2")
        self.assertEqual("RECOVERY_ACK_REQUIRED", caught.exception.code)

        ready = sop.acknowledge_recovery(
            recovered,
            acknowledged_by="operator",
            acknowledged_at="2026-08-26T01:17:00Z",
        )
        self.assertEqual("READY", ready["status"])
        resumed = claim(ready, owner_id="worker-b", claim_id="claim-2")
        self.assertEqual("worker-b", resumed["owner"]["owner_id"])

    def test_expired_owner_cannot_authorize_a_side_effect(self):
        state = claim(make_state())
        with self.assertRaises(sop.ContractViolation) as caught:
            sop.authorize_step(
                state,
                owner_id="worker-a",
                claim_id="claim-1",
                step_id="step-late",
                estimated_tokens=1,
                authorized_at="2026-08-26T01:16:00Z",
            )
        self.assertEqual("LEASE_EXPIRED", caught.exception.code)

    def test_step_authorization_persists_boundary_and_stops_before_budget_overrun(self):
        state = claim(make_state())
        admitted = sop.authorize_step(
            state,
            owner_id="worker-a",
            claim_id="claim-1",
            step_id="step-1",
            estimated_tokens=40,
            authorized_at="2026-08-26T01:01:00Z",
        )
        self.assertTrue(admitted["authorized"])
        state = admitted["state"]
        self.assertEqual("RUNNING", state["status"])
        self.assertEqual(1, state["usage"]["steps"])
        self.assertEqual(40, state["usage"]["tokens"])

        stopped = sop.authorize_step(
            state,
            owner_id="worker-a",
            claim_id="claim-1",
            step_id="step-2",
            estimated_tokens=61,
            authorized_at="2026-08-26T01:02:00Z",
        )
        self.assertFalse(stopped["authorized"])
        self.assertEqual("STOPPED", stopped["state"]["status"])
        self.assertEqual("BUDGET_LIMITED", stopped["state"]["stop_reason"])
        self.assertEqual(1, stopped["state"]["usage"]["steps"])

    def test_uncertain_side_effect_requires_recovery_and_known_failure_is_recorded(self):
        state = claim(make_state())
        state = sop.authorize_step(
            state,
            owner_id="worker-a",
            claim_id="claim-1",
            step_id="step-1",
            estimated_tokens=10,
            authorized_at="2026-08-26T01:01:00Z",
        )["state"]
        uncertain = sop.record_step_result(
            state,
            owner_id="worker-a",
            claim_id="claim-1",
            step_id="step-1",
            outcome="uncertain",
            recorded_at="2026-08-26T01:02:00Z",
            reason="external operation did not report a result",
        )
        self.assertEqual("RECOVERY_REQUIRED", uncertain["status"])
        self.assertEqual("SIDE_EFFECT_UNCERTAIN", uncertain["stop_reason"])

        state = claim(make_state())
        state = sop.authorize_step(
            state,
            owner_id="worker-a",
            claim_id="claim-1",
            step_id="step-1",
            estimated_tokens=10,
            authorized_at="2026-08-26T01:01:00Z",
        )["state"]
        failed = sop.record_step_result(
            state,
            owner_id="worker-a",
            claim_id="claim-1",
            step_id="step-1",
            outcome="failed",
            recorded_at="2026-08-26T01:02:00Z",
            reason="adapter rejected operation",
        )
        self.assertEqual("FAILED", failed["status"])
        self.assertEqual("EXECUTION_FAILED", failed["stop_reason"])
        self.assertEqual(1, failed["usage"]["failures"])

    def test_human_stop_requires_explicit_resume_and_review_is_not_auto_accepted(self):
        state = claim(make_state())
        stopped = sop.request_human_stop(
            state, actor="operator", stopped_at="2026-08-26T01:01:00Z", reason="pause"
        )
        self.assertEqual("STOPPED", stopped["status"])
        self.assertEqual("HUMAN_STOP", stopped["stop_reason"])
        ready = sop.resume_after_human_stop(
            stopped, resumed_by="operator", resumed_at="2026-08-26T01:02:00Z"
        )
        self.assertEqual("READY", ready["status"])

        state = claim(ready, owner_id="worker-b", claim_id="claim-2")
        review = sop.submit_for_review(
            state,
            owner_id="worker-b",
            claim_id="claim-2",
            submitted_at="2026-08-26T01:03:00Z",
        )
        self.assertEqual("WAITING_REVIEW", review["status"])
        with self.assertRaises(sop.ContractViolation) as caught:
            claim(review, owner_id="worker-c", claim_id="claim-3")
        self.assertEqual("REVIEW_REQUIRED", caught.exception.code)

    def test_contract_rejects_stale_mutation_without_changing_the_input(self):
        state = claim(make_state())
        before = {**state, "owner": dict(state["owner"]), "lease": dict(state["lease"])}
        with self.assertRaises(sop.ContractViolation) as caught:
            sop.authorize_step(
                state,
                owner_id="worker-a",
                claim_id="claim-1",
                step_id="step-1",
                estimated_tokens=1,
                authorized_at="2026-08-26T01:01:00Z",
                expected_revision=0,
            )
        self.assertEqual("STALE_STATE", caught.exception.code)
        self.assertEqual(before, state)


if __name__ == "__main__":
    unittest.main()

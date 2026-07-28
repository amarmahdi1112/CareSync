"""Actor-separated state rules for the canonical ATS and marketplace APIs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

HiringActor = Literal["employer", "candidate"]

JOB_STATUSES = frozenset({"draft", "open", "paused", "closed"})
APPLICATION_STATUSES = frozenset(
    {
        "invited",
        "applied",
        "screening",
        "interview",
        "offer",
        "accepted",
        "rejected",
        "withdrawn",
        "hired",
    }
)
OFFER_STATUSES = frozenset(
    {"draft", "sent", "accepted", "declined", "withdrawn", "superseded"}
)
INTERVIEW_STATUSES = frozenset(
    {
        "requested",
        "confirmed",
        "declined",
        "cancelled",
        "candidate_proposed",
        "proposal_declined",
    }
)

JOB_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"open", "closed"}),
    "open": frozenset({"paused", "closed"}),
    "paused": frozenset({"open", "closed"}),
    "closed": frozenset(),
}

# Candidate-owned actions never appear in the employer matrix. Interview and
# offer-specific commands use the narrower rules below.
EMPLOYER_APPLICATION_TRANSITIONS: dict[str, frozenset[str]] = {
    "invited": frozenset(),
    "applied": frozenset({"screening", "rejected"}),
    "screening": frozenset({"interview", "rejected"}),
    "interview": frozenset({"screening", "rejected"}),
    "offer": frozenset({"rejected"}),
    "accepted": frozenset(),
    "rejected": frozenset(),
    "withdrawn": frozenset(),
    "hired": frozenset(),
}

CANDIDATE_APPLICATION_TRANSITIONS: dict[str, frozenset[str]] = {
    "invited": frozenset(),
    "applied": frozenset({"withdrawn"}),
    "screening": frozenset({"withdrawn"}),
    "interview": frozenset({"withdrawn"}),
    "offer": frozenset({"accepted", "rejected", "withdrawn"}),
    "accepted": frozenset(),
    "rejected": frozenset(),
    "withdrawn": frozenset(),
    "hired": frozenset(),
}


@dataclass(frozen=True, slots=True)
class HiringLifecycleViolation(ValueError):
    status_code: int
    detail: str

    def __str__(self) -> str:
        return self.detail


def application_targets(actor: HiringActor, current: str) -> frozenset[str]:
    matrix = (
        EMPLOYER_APPLICATION_TRANSITIONS
        if actor == "employer"
        else CANDIDATE_APPLICATION_TRANSITIONS
    )
    return matrix.get(current, frozenset())


def require_job_transition(current: str, target: str) -> None:
    if target not in JOB_TRANSITIONS.get(current, frozenset()):
        raise HiringLifecycleViolation(409, f"Cannot move job from {current} to {target}")


def require_application_transition(
    actor: HiringActor,
    current: str,
    target: str,
) -> None:
    if target not in application_targets(actor, current):
        raise HiringLifecycleViolation(
            409,
            f"{actor.title()} cannot move application from {current} to {target}",
        )


def require_candidate_withdrawal(current: str) -> None:
    require_application_transition("candidate", current, "withdrawn")


def require_offer_creation(application_status: str) -> None:
    if application_status not in {"interview", "offer"}:
        raise HiringLifecycleViolation(409, "Offers require an interviewed application")


def require_employer_offer_withdrawal(application_status: str, offer_status: str) -> None:
    if offer_status != "sent":
        raise HiringLifecycleViolation(409, "Only a sent offer may receive a decision")
    if application_status != "offer":
        raise HiringLifecycleViolation(
            409,
            "Application is no longer awaiting this offer decision",
        )


def require_candidate_offer_decision(
    application_status: str,
    offer_status: str,
    decision: str,
) -> None:
    if decision not in {"accepted", "declined"}:
        raise HiringLifecycleViolation(422, "Decision must be accepted or declined")
    if offer_status != "sent" or application_status != "offer":
        raise HiringLifecycleViolation(
            409,
            "Only the current sent offer may receive a decision",
        )
    require_application_transition(
        "candidate",
        application_status,
        "accepted" if decision == "accepted" else "rejected",
    )


def require_interview_request(
    application_status: str,
    candidate_consent_status: str,
) -> None:
    if candidate_consent_status != "accepted" or application_status not in {
        "applied",
        "screening",
    }:
        raise HiringLifecycleViolation(
            409,
            "Candidate consent and an active application are required",
        )


def require_candidate_interview_decision(
    application_status: str,
    interview_status: str,
    decision: str,
) -> None:
    if decision not in {"confirmed", "declined", "proposed"}:
        raise HiringLifecycleViolation(
            422,
            "Decision must be confirmed, declined, or proposed",
        )
    if interview_status != "requested":
        raise HiringLifecycleViolation(409, "Interview already received a decision")
    if application_status not in {"screening", "interview"}:
        raise HiringLifecycleViolation(
            409,
            "Application is no longer eligible for interview response",
        )


def require_employer_proposal_decision(
    application_status: str,
    interview_status: str,
    *,
    has_candidate_proposal: bool,
    decision: str,
) -> None:
    if decision not in {"accepted", "declined", "countered"}:
        raise HiringLifecycleViolation(
            422,
            "Decision must be accepted, declined, or countered",
        )
    if interview_status != "candidate_proposed" or not has_candidate_proposal:
        raise HiringLifecycleViolation(
            409,
            "No candidate time proposal is awaiting review",
        )
    if application_status != "screening":
        raise HiringLifecycleViolation(
            409,
            "Application is no longer eligible for proposal review",
        )


def require_provisioning(application_status: str) -> None:
    if application_status != "accepted":
        raise HiringLifecycleViolation(409, "Only an accepted candidate can be provisioned")

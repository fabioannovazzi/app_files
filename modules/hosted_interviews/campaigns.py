from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "AI_ADOPTION_RESEARCH_CAMPAIGN_ID",
    "CLARA_NEEDS_RESEARCH_CAMPAIGN_ID",
    "CLARA_NEEDS_RESEARCH_OBJECTIVE",
    "CLARA_NEEDS_RESEARCH_PARTICIPANT_INTRO",
    "COMMERCIALISTI_AI_WORKING_GROUP_CAMPAIGN_ID",
    "COMMERCIALISTI_AI_WORKING_GROUP_OBJECTIVE",
    "COMMERCIALISTI_AI_WORKING_GROUP_PARTICIPANT_INTRO",
    "InterviewCampaignDefinition",
    "LEGACY_UNCLASSIFIED_CAMPAIGN_ID",
    "UnknownInterviewCampaignError",
    "build_campaign_interview_payload",
    "build_outreach_interview_case_id",
    "get_interview_campaign",
    "list_interview_campaigns",
    "outreach_interviewee_role",
]


AI_ADOPTION_RESEARCH_CAMPAIGN_ID = "professional-firms-ai-adoption-research-v1"
CLARA_NEEDS_RESEARCH_CAMPAIGN_ID = "clara-needs-research-v1"
CLARA_NEEDS_RESEARCH_OBJECTIVE = (
    "Understand which tasks each participant would want to entrust to Clara, "
    "which current capabilities they would use, which results they expect, and "
    "which improvements or additions would make Clara worth using."
)
CLARA_NEEDS_RESEARCH_PARTICIPANT_INTRO = (
    "Un intervistatore AI ti chiederà quali attività vorresti affidare a Clara, "
    "quali risultati ti aspetti e quali funzioni mancano. Le tue risposte ci "
    "aiuteranno a decidere che cosa migliorare e che cosa aggiungere."
)
COMMERCIALISTI_AI_WORKING_GROUP_CAMPAIGN_ID = "commercialisti-ai-working-group-v1"
COMMERCIALISTI_AI_WORKING_GROUP_OBJECTIVE = (
    "Understand where commercialisti want AI to support their work, what they "
    "need, what AI currently delivers well or poorly, and the gap between the "
    "two—so the plugins can address real unmet professional needs."
)
COMMERCIALISTI_AI_WORKING_GROUP_PARTICIPANT_INTRO = (
    "Questa breve intervista serve a capire in quali attività dello studio "
    "l'AI potrebbe essere davvero utile, che cosa offre già oggi, che cosa non "
    "funziona e quali esigenze professionali restano ancora senza risposta."
)
LEGACY_UNCLASSIFIED_CAMPAIGN_ID = "legacy-unclassified-v1"


class UnknownInterviewCampaignError(ValueError):
    """Raised when an exact interview campaign ID is not registered."""


@dataclass(frozen=True)
class InterviewCampaignDefinition:
    """Immutable, versioned brief shared by interviews in one campaign."""

    interview_campaign_id: str
    name: str
    description: str
    case_name: str
    client_project: str
    interview_title: str
    default_interviewee_role: str
    interview_mode: str
    purpose: str
    background_context: str
    priority_topics: tuple[str, ...]
    boundaries: tuple[str, ...]
    participant_intro: str = ""

    def prepared_payload(
        self,
        *,
        case_id: str,
        language: str,
        participant_name: str = "",
        interviewee_role: str = "",
        expires_in_hours: int = 7 * 24,
    ) -> dict[str, Any]:
        """Return an independent prepared-interview payload for this campaign."""

        return {
            "interview_campaign_id": self.interview_campaign_id,
            "case_id": case_id,
            "case_name": self.case_name,
            "participant_name": participant_name,
            "client_project": self.client_project,
            "interview_title": self.interview_title,
            "interviewee_role": interviewee_role or self.default_interviewee_role,
            "interview_mode": self.interview_mode,
            "language": language,
            "purpose": self.purpose,
            "participant_intro": self.participant_intro,
            "background_context": self.background_context,
            "hypotheses_to_test": [],
            "priority_topics": list(self.priority_topics),
            "questions": [],
            "red_flags": [],
            "boundaries": list(self.boundaries),
            "expires_in_hours": expires_in_hours,
        }


_CAMPAIGNS = (
    InterviewCampaignDefinition(
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        name="Professional firms AI adoption research",
        description=(
            "Comparative research on current AI use, limits, trust, and adoption "
            "barriers across professional firms."
        ),
        case_name="AI adoption research interview",
        client_project="Commercialisti and professional firms AI adoption research",
        interview_title="AI adoption in professional firms",
        default_interviewee_role="Professional firm representative",
        interview_mode="research",
        purpose=(
            "Run a clean research interview about how professional firms use AI in "
            "daily work. Understand real use cases, limits, trust, confidentiality, "
            "adoption barriers, and language participants use to describe value and "
            "risk."
        ),
        background_context=(
            "This participant came from an outreach research invitation. Do not "
            "mention products, plugins, installation, beta testing, sales, or "
            "purchasing. The promised output is a comparative research synthesis."
        ),
        priority_topics=(
            "Current AI tools or practices used in the firm",
            "Concrete tasks where AI already helps",
            "Tasks where AI is not trusted or not appropriate",
            "Client-facing versus internal use",
            (
                "Confidentiality, privacy, professional responsibility, and "
                "accuracy concerns"
            ),
            "Adoption barriers inside the firm",
            "What would make AI genuinely useful in daily professional work",
            (
                "Language and examples the participant uses to describe AI value "
                "and risk"
            ),
        ),
        boundaries=(
            "Do not ask for confidential client details.",
            (
                "Do not mention products, plugins, installation, beta testing, "
                "sales, or purchasing."
            ),
            "Keep the interview as professional research.",
        ),
    ),
    InterviewCampaignDefinition(
        interview_campaign_id=CLARA_NEEDS_RESEARCH_CAMPAIGN_ID,
        name="Clara needs research",
        description=(
            "Research on the Clara capabilities each invited participant would "
            "use, improve, or add."
        ),
        case_name="Clara needs interview",
        client_project="Clara product needs research",
        interview_title="Intervista su Clara",
        default_interviewee_role="Clara invitee",
        interview_mode="research",
        purpose=CLARA_NEEDS_RESEARCH_OBJECTIVE,
        background_context=(
            "This participant received an invitation to try Clara. They may be a "
            "consultant, another kind of professional, or primarily interested in "
            "one capability such as creating and editing presentations. This is a "
            "product-needs interview about Clara, not a test of how well the "
            "participant already understands it. Begin with the first concrete thing "
            "they would want to ask Clara to do. When evaluating current capabilities, "
            "describe them briefly in plain language before asking for a reaction."
        ),
        priority_topics=(
            "The first concrete task the participant would want to ask Clara to do",
            (
                "Usefulness of Clara's current capabilities: creating or revising "
                "presentations, following a visual reference, conducting a remote "
                "voice interview, transcribing recordings, and continuing a project "
                "across Codex sessions"
            ),
            "The source material the participant would provide and the output expected",
            "What would make a result from Clara successful and usable",
            "Current capabilities that should be improved and functions that are missing",
            "Expectations about review, control, confidentiality, and trust",
            "Obstacles in access, installation, and the first use of Clara",
        ),
        boundaries=(
            "The interview has a hard maximum of 15 minutes.",
            "Do not assume the participant is a consultant.",
            (
                "Do not open with broad questions about the participant's role, work, "
                "or current workflow. Ask about concrete things they would want Clara "
                "to do."
            ),
            (
                "Before asking the participant to evaluate an existing Clara "
                "capability, describe that capability briefly in plain language. Do "
                "not test product knowledge."
            ),
            "Do not turn the interview into generic AI-adoption research.",
            "Do not ask for confidential client details or file uploads.",
            "Do not pitch, sell, or seek a purchase or pilot commitment.",
        ),
        participant_intro=CLARA_NEEDS_RESEARCH_PARTICIPANT_INTRO,
    ),
    InterviewCampaignDefinition(
        interview_campaign_id=COMMERCIALISTI_AI_WORKING_GROUP_CAMPAIGN_ID,
        name="Commercialisti AI Working Group",
        description=("Needs discovery for the Commercialisti AI Working Group."),
        case_name="Commercialisti AI Working Group",
        client_project="Commercialisti AI Working Group",
        interview_title="AI nel lavoro dello studio",
        default_interviewee_role=(
            "Commercialista or Italian professional firm representative"
        ),
        interview_mode="research",
        purpose=COMMERCIALISTI_AI_WORKING_GROUP_OBJECTIVE,
        background_context=(
            "This participant is part of the Commercialisti AI Working Group. "
            "This is needs discovery, not a generic AI adoption survey, product "
            "pitch, or pilot-selection interview. Learn how the participant wants "
            "AI to help in their own language without steering them toward the "
            "existing plugin portfolio."
        ),
        priority_topics=(
            "Work and professional processes where the participant wants AI support",
            "What the participant needs AI to provide in that work",
            "What AI currently delivers well in those situations",
            "What AI currently delivers poorly or not at all",
            "The gap between the participant's needs and current AI support",
            "What genuinely useful AI assistance would look like",
        ),
        boundaries=(
            "Do not ask for confidential client details.",
            "Do not ask the participant to provide or upload files or a real case.",
            (
                "Do not ask which process they would test first or seek a pilot "
                "commitment."
            ),
            "Do not pitch products or steer answers toward existing plugins.",
        ),
        participant_intro=COMMERCIALISTI_AI_WORKING_GROUP_PARTICIPANT_INTRO,
    ),
)

# Campaign IDs are exact audit keys. A duplicate would make one brief ambiguous.
if len({campaign.interview_campaign_id for campaign in _CAMPAIGNS}) != len(
    _CAMPAIGNS
):  # pragma: no cover - import-time configuration guard
    raise RuntimeError("Interview campaign IDs must be unique.")

_CAMPAIGNS_BY_ID = {campaign.interview_campaign_id: campaign for campaign in _CAMPAIGNS}


def list_interview_campaigns() -> tuple[InterviewCampaignDefinition, ...]:
    """Return registered interview campaigns in stable display order."""

    return _CAMPAIGNS


def get_interview_campaign(
    interview_campaign_id: str,
) -> InterviewCampaignDefinition:
    """Resolve an exact campaign ID without semantic or default fallback."""

    try:
        return _CAMPAIGNS_BY_ID[interview_campaign_id]
    except KeyError as exc:
        raise UnknownInterviewCampaignError(
            f"Unknown interview campaign: {interview_campaign_id}"
        ) from exc


def build_campaign_interview_payload(
    interview_campaign_id: str,
    *,
    case_id: str,
    language: str,
    participant_name: str = "",
    interviewee_role: str = "",
    expires_in_hours: int = 7 * 24,
) -> dict[str, Any]:
    """Build one independent interview payload from an exact campaign brief."""

    campaign = get_interview_campaign(interview_campaign_id)
    return campaign.prepared_payload(
        case_id=case_id,
        language=language,
        participant_name=participant_name,
        interviewee_role=interviewee_role,
        expires_in_hours=expires_in_hours,
    )


def build_outreach_interview_case_id(
    outreach_campaign_id: str,
    participant_hash: str,
) -> str:
    """Build the non-PII case ID for one outreach campaign participant."""

    campaign = "-".join(outreach_campaign_id.split()).strip("-")[:96]
    suffix = participant_hash[:16] or "participant"
    return f"{campaign or 'outreach'}-{suffix}"[:120]


def outreach_interviewee_role(locale: str, quota_key: str) -> str:
    """Return the factual market role label used in an outreach interview."""

    if locale == "italy" or quota_key == "italy-organization":
        return "Commercialista or Italian professional firm representative"
    if locale == "swiss-romande":
        return "Fiduciaire or Swiss Romande professional firm representative"
    if locale == "swiss-german":
        return "Treuhand or Swiss German professional firm representative"
    if locale == "uk":
        return "Accountant or UK professional firm representative"
    return "Professional firm representative"

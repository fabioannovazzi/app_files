from __future__ import annotations

import pytest

from modules.hosted_interviews.campaigns import (
    AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
    CLARA_NEEDS_RESEARCH_CAMPAIGN_ID,
    CLARA_NEEDS_RESEARCH_OBJECTIVE,
    CLARA_NEEDS_RESEARCH_PARTICIPANT_INTRO,
    COMMERCIALISTI_AI_WORKING_GROUP_CAMPAIGN_ID,
    COMMERCIALISTI_AI_WORKING_GROUP_OBJECTIVE,
    COMMERCIALISTI_AI_WORKING_GROUP_PARTICIPANT_INTRO,
    UnknownInterviewCampaignError,
    build_campaign_interview_payload,
    build_outreach_interview_case_id,
    get_interview_campaign,
    list_interview_campaigns,
)


def test_interview_campaign_registry_contains_unique_expected_ids() -> None:
    campaigns = list_interview_campaigns()

    campaign_ids = [campaign.interview_campaign_id for campaign in campaigns]
    assert campaign_ids == [
        AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        CLARA_NEEDS_RESEARCH_CAMPAIGN_ID,
        COMMERCIALISTI_AI_WORKING_GROUP_CAMPAIGN_ID,
    ]
    assert len(campaign_ids) == len(set(campaign_ids))


def test_get_interview_campaign_requires_an_exact_registered_id() -> None:
    unknown_campaign_id = "commercialisti-ai-needs"

    with pytest.raises(
        UnknownInterviewCampaignError,
        match=f"Unknown interview campaign: {unknown_campaign_id}",
    ):
        get_interview_campaign(unknown_campaign_id)


def test_build_ai_adoption_campaign_payload_contains_only_adoption_brief() -> None:
    payload = build_campaign_interview_payload(
        AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        case_id="adoption-participant",
        language="it",
    )

    assert payload["interview_campaign_id"] == AI_ADOPTION_RESEARCH_CAMPAIGN_ID
    assert "how professional firms use AI" in payload["purpose"]
    assert "Adoption barriers inside the firm" in payload["priority_topics"]
    assert (
        "The gap between the participant's needs and current AI support"
        not in payload["priority_topics"]
    )
    assert "plugin participant onboarding" not in payload["client_project"]


def test_build_working_group_payload_contains_only_needs_brief() -> None:
    payload = build_campaign_interview_payload(
        COMMERCIALISTI_AI_WORKING_GROUP_CAMPAIGN_ID,
        case_id="needs-participant",
        language="it",
    )
    assert (
        payload["interview_campaign_id"] == COMMERCIALISTI_AI_WORKING_GROUP_CAMPAIGN_ID
    )
    assert payload["purpose"] == COMMERCIALISTI_AI_WORKING_GROUP_OBJECTIVE
    assert (
        payload["participant_intro"]
        == COMMERCIALISTI_AI_WORKING_GROUP_PARTICIPANT_INTRO
    )
    assert payload["participant_intro"].startswith("Questa breve intervista")
    assert "what AI currently delivers well or poorly" in payload["purpose"]
    assert "gap between the two" in payload["purpose"]
    assert (
        "The gap between the participant's needs and current AI support"
        in payload["priority_topics"]
    )
    assert "Adoption barriers inside the firm" not in payload["priority_topics"]
    assert payload["questions"] == []
    assert (
        "Do not ask which process they would test first or seek a pilot commitment."
        in payload["boundaries"]
    )


def test_build_clara_needs_payload_centers_clara_without_assuming_consulting() -> None:
    payload = build_campaign_interview_payload(
        CLARA_NEEDS_RESEARCH_CAMPAIGN_ID,
        case_id="clara-invitee",
        language="it",
    )

    assert payload["purpose"] == CLARA_NEEDS_RESEARCH_OBJECTIVE
    assert payload["participant_intro"] == CLARA_NEEDS_RESEARCH_PARTICIPANT_INTRO
    assert payload["interview_title"] == "Intervista su Clara"
    assert payload["participant_intro"].startswith("Un intervistatore AI")
    assert "attività vorresti affidare a Clara" in payload["participant_intro"]
    assert any("presentation" in topic for topic in payload["priority_topics"])
    assert any(
        "functions that are missing" in topic for topic in payload["priority_topics"]
    )
    assert "The interview has a hard maximum of 15 minutes." in payload["boundaries"]
    assert "Do not assume the participant is a consultant." in payload["boundaries"]
    assert any(
        "Do not open with broad questions" in item for item in payload["boundaries"]
    )
    assert (
        "Do not turn the interview into generic AI-adoption research."
        in payload["boundaries"]
    )
    assert "Clara-adjacent" not in str(payload)
    assert "Non occorre" not in payload["participant_intro"]
    assert payload["questions"] == []


def test_build_campaign_payload_returns_independent_list_values() -> None:
    first_payload = build_campaign_interview_payload(
        COMMERCIALISTI_AI_WORKING_GROUP_CAMPAIGN_ID,
        case_id="first-participant",
        language="it",
    )
    first_payload["priority_topics"].append("Mutation sentinel")

    second_payload = build_campaign_interview_payload(
        COMMERCIALISTI_AI_WORKING_GROUP_CAMPAIGN_ID,
        case_id="second-participant",
        language="it",
    )

    assert "Mutation sentinel" not in second_payload["priority_topics"]


def test_build_outreach_interview_case_id_separates_outreach_campaigns() -> None:
    participant_hash = "0123456789abcdef-rest"

    first_case_id = build_outreach_interview_case_id(
        "legacy-adoption-2026-07", participant_hash
    )
    second_case_id = build_outreach_interview_case_id(
        "commercialisti-needs-2026-07", participant_hash
    )

    assert first_case_id == "legacy-adoption-2026-07-0123456789abcdef"
    assert second_case_id == "commercialisti-needs-2026-07-0123456789abcdef"
    assert first_case_id != second_case_id

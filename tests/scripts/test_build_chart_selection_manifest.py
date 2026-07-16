from __future__ import annotations

from scripts.build_chart_selection_manifest import build_chart_selection_manifest


def _artifact_by_label(manifest: dict, label: str) -> dict:
    return next(
        artifact for artifact in manifest["artifacts"] if artifact["label"] == label
    )


def test_build_chart_selection_manifest_has_selection_examples_for_every_capability() -> (
    None
):
    manifest = build_chart_selection_manifest()
    capabilities = manifest["capabilities"]

    assert not manifest["validation_issues"]
    assert len(capabilities) == 48

    for capability_id, capability in capabilities.items():
        examples = capability["selection_examples"]

        assert examples["positive_questions"], capability_id
        assert examples["negative_questions"], capability_id
        assert examples["ambiguous_questions"], capability_id
        assert (
            capability_id
            in examples["ambiguous_questions"][0]["candidate_capability_ids"]
        )
        for negative in examples["negative_questions"]:
            assert negative["better_capability_id"] != capability_id
            assert negative["question"] not in examples["positive_questions"]


def test_build_chart_selection_manifest_examples_preserve_dangerous_distinctions() -> (
    None
):
    manifest = build_chart_selection_manifest()
    capabilities = manifest["capabilities"]

    trend_examples = capabilities["period_comparison.trend"]["selection_examples"]
    scatter_examples = capabilities["scatter.scatter"]["selection_examples"]
    fixed_bridge_examples = capabilities["variance.exploded_variance_bridge"][
        "selection_examples"
    ]
    root_cause_exploded_examples = capabilities["variance.root_cause_exploded_bridge"][
        "selection_examples"
    ]

    assert trend_examples["positive_questions"] == [
        "How did monthly cosmetics sales evolve versus previous year?"
    ]
    assert any(
        negative["better_capability_id"] == "scatter.bubble"
        for negative in scatter_examples["negative_questions"]
    )
    assert any(
        negative["better_capability_id"] == "variance.root_cause_exploded_bridge"
        for negative in fixed_bridge_examples["negative_questions"]
    )
    assert any(
        negative["better_capability_id"] == "variance.exploded_variance_bridge"
        for negative in root_cause_exploded_examples["negative_questions"]
    )


def test_build_chart_selection_manifest_pairwise_ambiguity_audit_passes() -> None:
    manifest = build_chart_selection_manifest()
    pairwise = manifest["selector_audit"]["pairwise_ambiguity"]

    assert pairwise["result"] == "pass"
    assert pairwise["unresolved_pair_count"] == 0
    assert pairwise["high_overlap_pair_count"] == 21

    groups = {tuple(group["capability_ids"]) for group in pairwise["signature_groups"]}
    assert (
        "period_comparison.by_period",
        "period_comparison.multitier_column",
        "period_comparison.trend",
    ) in groups
    assert (
        "variance.exploded_variance_bridge",
        "variance.root_cause_component_bridge",
    ) in groups
    assert (
        "mix.cohort_lost_stacked_column",
        "mix.cohort_since_stacked_column",
        "mix.like_for_like_column",
    ) in groups
    for pair in pairwise["high_overlap_pairs"]:
        left_id, right_id = pair["capability_ids"]
        cues = pair["structured_decision_cues"]
        assert (
            cues[left_id]["requires_question_focus"]
            != cues[right_id]["requires_question_focus"]
        )
        assert (
            cues[left_id]["forbidden_question_focus"]
            != cues[right_id]["forbidden_question_focus"]
        )


def test_build_chart_selection_manifest_competitor_links_are_symmetric() -> None:
    manifest = build_chart_selection_manifest()
    capabilities = manifest["capabilities"]

    asymmetric_links = [
        (capability_id, competitor_id)
        for capability_id, capability in capabilities.items()
        for competitor_id in capability["competing_capability_ids"]
        if capability_id not in capabilities[competitor_id]["competing_capability_ids"]
    ]

    assert asymmetric_links == []


def test_build_chart_selection_manifest_attribute_tables_list_sibling_competitors() -> (
    None
):
    manifest = build_chart_selection_manifest()
    capabilities = manifest["capabilities"]
    attribute_capability_ids = {
        capability_id
        for capability_id, capability in capabilities.items()
        if capability["family"] == "attributes"
    }

    for capability_id in attribute_capability_ids:
        competitors = set(capabilities[capability_id]["competing_capability_ids"])
        assert competitors >= attribute_capability_ids - {capability_id}


def test_build_chart_selection_manifest_has_structured_decision_cues() -> None:
    manifest = build_chart_selection_manifest()

    for capability_id, capability in manifest["capabilities"].items():
        assert isinstance(capability["primary_decision_cue"], str), capability_id
        assert capability["primary_decision_cue"].strip(), capability_id
        for field in (
            "requires_question_focus",
            "reject_decision_cues",
            "forbidden_question_focus",
        ):
            values = capability[field]
            assert isinstance(values, list), capability_id
            assert values, capability_id
            assert all(isinstance(value, str) and value.strip() for value in values)

    trend = manifest["capabilities"]["period_comparison.trend"]
    assert trend["requires_question_focus"] == [
        "trajectory_shape",
        "current_vs_baseline_period_axis",
    ]
    assert "bridge_reconciliation" in trend["forbidden_question_focus"]

    pvm = manifest["capabilities"]["variance.price_volume_mix"]
    assert pvm["requires_question_focus"] == [
        "pvm_decomposition",
        "price_volume_mix",
    ]
    assert "dimension_variance" in pvm["forbidden_question_focus"]


def test_build_chart_selection_manifest_has_no_capability_coverage_gaps() -> None:
    manifest = build_chart_selection_manifest()

    assert manifest["coverage_gaps"] == {
        "generated_manifest_capabilities_without_gallery_examples": [],
        "gallery_capabilities_without_generated_manifest_records": [],
    }
    assert (
        manifest["counts"]["generated_manifest_capabilities_without_gallery_examples"]
        == 0
    )

    capabilities = manifest["capabilities"]
    for capability_id in (
        "mix.area",
        "mix.barmekko",
        "mix.marimekko",
        "mix.pareto",
        "mix.stacked_pareto",
        "mix.timeline",
        "period_comparison.by_period",
        "set_overlap.upset",
        "set_overlap.upset_small_multiples",
        "set_overlap.venn",
        "variance.price_volume_mix",
        "variance.scenario_bridge",
    ):
        assert capabilities[capability_id]["present_in_gallery_manifest"], capability_id
        assert capabilities[capability_id][
            "present_in_generated_manifest"
        ], capability_id

    assert any(
        artifact["label"] == "period / year_over_year_by_recency_window"
        and artifact["capability_id"] == "period_comparison.by_period"
        for artifact in manifest["artifacts"]
    )
    assert any(
        artifact["label"] == "period / year_over_year_small_multiples"
        and artifact["capability_id"] == "period_comparison.trend"
        for artifact in manifest["artifacts"]
    )


def test_price_volume_mix_does_not_require_business_dimension() -> None:
    manifest = build_chart_selection_manifest()
    pvm = manifest["capabilities"]["variance.price_volume_mix"]
    requirements = pvm["selection_contract"]["dataset_requirements"]

    assert requirements["dimensions"]["minimum_count"] == 0
    assert requirements["dimensions"]["required_roles"] == ["period_or_scenario_pair"]
    assert "mix_dimension" not in requirements["dimensions"]["role_requirements"]

    mix_effect = next(
        role
        for role in requirements["metrics"]["derived_metric_roles"]
        if role["role"] == "mix_effect"
    )
    assert mix_effect["produced_from"] == [
        "value_metric",
        "volume_metric",
        "price_or_rate_metric",
    ]
    assert "not a required dataset dimension parameter" in mix_effect["derivation"]


def test_funnel_stage_table_does_not_claim_period_filtering() -> None:
    manifest = build_chart_selection_manifest()
    funnel = manifest["capabilities"]["funnel.stage_table"]
    requirements = funnel["selection_contract"]["dataset_requirements"]

    assert funnel["period_semantics"] == {
        "role": "none",
        "supports_period_axis": False,
        "supports_period_filter": False,
    }
    assert requirements["period"] == {
        "role": "none",
        "requires_period_axis": False,
        "allows_period_filter": False,
    }


def test_artifacts_expose_rendering_variant_metadata() -> None:
    manifest = build_chart_selection_manifest()

    for artifact in manifest["artifacts"]:
        variant = artifact["rendering_variant"]
        assert variant["output_form"], artifact["label"]
        assert variant["layout_variant"], artifact["label"]
        assert variant["encoding_variant"], artifact["label"]
        assert variant["selector_level"] in {
            "base_capability",
            "capability_choice",
            "rendering_variant_choice",
        }
        assert isinstance(variant["variant_changes_capability_selection"], bool)
        assert isinstance(variant["adds_parameter_roles"], list)
        assert isinstance(variant["variant_selection_cues"], list)


def test_manifest_exposes_role_registry_and_invocation_contracts() -> None:
    manifest = build_chart_selection_manifest()

    role_registry = manifest["role_registry"]
    assert role_registry["counts"]["chart_roles_missing_mapping"] == 0
    assert "primary_metric" in role_registry["chart_roles"]
    assert "direct_dimension" in role_registry["profile_roles"]

    for capability_id, capability in manifest["capabilities"].items():
        invocation = capability["normalized_invocation_contract"]
        assert invocation["capability_id"] == capability_id
        assert invocation["status"] == "parameter_contract_ready"
        assert invocation["required_role_contracts"], capability_id
        assert invocation["boundary"].startswith("Mechanical invocation contract")

    overlay = manifest["capabilities"]["mix.column_overlay"][
        "normalized_invocation_contract"
    ]
    assert any(
        contract["role"] == "related_marker_metric"
        for contract in overlay["required_role_contracts"]
        + overlay["variant_role_contracts"]
    )


def test_small_multiples_are_rendering_variants_unless_panel_is_the_capability() -> (
    None
):
    manifest = build_chart_selection_manifest()

    histogram = _artifact_by_label(manifest, "distribution / histogram_small_multiples")
    histogram_variant = histogram["rendering_variant"]
    assert histogram["capability_id"] == "distribution.histogram"
    assert histogram_variant["layout_variant"] == "small_multiples"
    assert histogram_variant["selector_level"] == "rendering_variant_choice"
    assert histogram_variant["variant_changes_capability_selection"] is False
    assert histogram_variant["adds_parameter_roles"] == ["panel_dimension"]

    upset_panels = _artifact_by_label(
        manifest,
        "set_overlap / set_overlap_small_multiples / upset_small_multiples",
    )
    upset_variant = upset_panels["rendering_variant"]
    assert upset_panels["capability_id"] == "set_overlap.upset_small_multiples"
    assert upset_variant["layout_variant"] == "small_multiples"
    assert upset_variant["selector_level"] == "capability_choice"
    assert upset_variant["variant_changes_capability_selection"] is True
    assert "panel_dimension" in upset_variant["adds_parameter_roles"]


def test_overlays_are_capability_choices_with_related_marker_metric() -> None:
    manifest = build_chart_selection_manifest()

    overlay = _artifact_by_label(manifest, "mix_comparison / related_metrics_bar")
    variant = overlay["rendering_variant"]

    assert overlay["capability_id"] == "mix.stacked_bar_overlay"
    assert variant["encoding_variant"] == "overlay"
    assert variant["selector_level"] == "capability_choice"
    assert variant["variant_changes_capability_selection"] is True
    assert variant["adds_parameter_roles"] == ["related_marker_metric"]

    overlay_panels = _artifact_by_label(
        manifest,
        "mix_comparison / related_metrics_bar_small_multiples",
    )
    panel_variant = overlay_panels["rendering_variant"]
    assert panel_variant["selector_level"] == "capability_choice"
    assert panel_variant["variant_changes_capability_selection"] is True
    assert set(panel_variant["adds_parameter_roles"]) == {
        "panel_dimension",
        "related_marker_metric",
    }


def test_like_for_like_is_capability_not_rendering_variant_of_column() -> None:
    manifest = build_chart_selection_manifest()

    like_for_like = _artifact_by_label(
        manifest,
        "mix_like_for_like / like_for_like_column_total",
    )
    variant = like_for_like["rendering_variant"]

    assert like_for_like["capability_id"] == "mix.like_for_like_column"
    assert variant["selector_level"] == "base_capability"
    assert variant["variant_changes_capability_selection"] is False
    assert variant["encoding_variant"] == "like_for_like"

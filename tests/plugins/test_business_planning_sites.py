"""The hosted candidate preserves verified figures, readers and prior versions."""

import hashlib
import json
from copy import deepcopy

import pytest

from tests.plugins.test_business_planning_presentation import (
    bind_reporting_component,
    comparison_case,
)
from tests.plugins.test_business_planning_shared import (
    FIXTURE,
    PlanningError,
    bind_plugin_imports,
    build_plan,
    compile_html,
)


def interactive_case():
    case = comparison_case()
    second = deepcopy(case["presentation"]["tables"][0])
    second["id"] = "second"
    second["title"] = "Febbraio · Avverso rispetto alla base"
    for row in second["rows"]:
        for cell in row[1:]:
            cell["calculation_ids"] = [
                cid.replace("2027-01", "2027-02") for cid in cell["calculation_ids"]
            ]
    case["presentation"]["tables"].append(second)
    case["presentation"]["comparison_groups"] = [
        {
            "id": "profit",
            "title": "Conto economico",
            "views": [
                {
                    "table_id": "forecast-comparison",
                    "period": "Gennaio",
                    "scenario": "Avverso / Base",
                },
                {
                    "table_id": "second",
                    "period": "Febbraio",
                    "scenario": "Avverso / Base",
                },
            ],
        }
    ]
    return case


def test_site_matches_compiler_bytes_and_contains_only_report_public_asset(tmp_path):
    from planning_site import prepare_site

    plan = build_plan(interactive_case(), source_root=FIXTURE)
    destination = tmp_path / "site"

    receipt = prepare_site(
        plan, source_root=FIXTURE, output=destination, audience="internal"
    )

    report = (destination / "dist/index.html").read_bytes()
    assert report == compile_html(plan, source_root=FIXTURE).encode("utf-8")
    assert receipt["report_sha256"] == hashlib.sha256(report).hexdigest()
    assert receipt["publication_status"] == "prepared_not_published"
    assert sorted(p.name for p in (destination / "dist").iterdir()) == ["index.html"]
    assert json.loads((destination / ".openai/hosting.json").read_text()) == {
        "static": {"directory": "dist"}
    }
    assert report.count(b"data-comparison-panel data-period=") == 2
    assert b"base/2027-02/revenue" in report
    assert "Stampa la vista corrente" in report.decode()


@pytest.mark.parametrize(
    "problem, message",
    [
        ("audience", "Site audience differs"),
        ("tampered", "calculated|replay|hash|differs|altered"),
        ("restriction", "Audience restriction"),
    ],
)
def test_invalid_publication_candidate_writes_nothing(tmp_path, problem, message):
    from planning_site import prepare_site

    case = interactive_case()
    if problem == "restriction":
        case["audience"] = "customer"
    plan = build_plan(case, source_root=FIXTURE)
    if problem == "tampered":
        plan["calculations"]["base/2027-01/revenue"]["value"] = "9999"
    audience = "customer" if problem in {"audience", "restriction"} else "internal"
    destination = tmp_path / "site"

    with pytest.raises(PlanningError, match=message):
        prepare_site(plan, source_root=FIXTURE, output=destination, audience=audience)

    assert not destination.exists()


def test_repeated_site_export_preserves_previous_version(tmp_path):
    from planning_site import prepare_site

    plan = build_plan(interactive_case(), source_root=FIXTURE)
    destination = tmp_path / "site"
    destination.mkdir()
    (destination / "retained.txt").write_text("previous version")

    with pytest.raises(PlanningError, match="fresh Sites output"):
        prepare_site(plan, source_root=FIXTURE, output=destination, audience="internal")

    assert (destination / "retained.txt").read_text() == "previous version"


def test_site_cli_replays_saved_report_and_requires_matching_readers(tmp_path):
    from planning_site import main

    plan = build_plan(interactive_case(), source_root=FIXTURE)
    saved = tmp_path / "business_plan.json"
    saved.write_text(json.dumps(plan))
    destination = tmp_path / "site"

    result = main(
        [
            "--plan",
            str(saved),
            "--source-root",
            str(FIXTURE),
            "--audience",
            "internal",
            "--output-dir",
            str(destination),
        ]
    )

    assert result == 0
    assert (destination / "dist/index.html").is_file()


def test_site_cli_malformed_saved_report_exits_without_public_files(tmp_path):
    from planning_site import main

    saved = tmp_path / "invalid.json"
    saved.write_text("not JSON")
    destination = tmp_path / "site"

    with pytest.raises(SystemExit) as result:
        main(
            [
                "--plan",
                str(saved),
                "--source-root",
                str(FIXTURE),
                "--audience",
                "internal",
                "--output-dir",
                str(destination),
            ]
        )

    assert result.value.code == 2
    assert not destination.exists()


def test_blocked_plan_cannot_be_exported_as_site(tmp_path):
    from planning_site import prepare_site

    case = interactive_case()
    case["narrative"][0]["claims"]["ebitda"]["value"] = "9999"
    plan = build_plan(case, source_root=FIXTURE)

    with pytest.raises(PlanningError, match="blocked report"):
        prepare_site(
            plan, source_root=FIXTURE, output=tmp_path / "site", audience="internal"
        )

    assert not (tmp_path / "site").exists()


def test_selector_labels_are_escaped_and_all_views_remain_in_source():
    case = interactive_case()
    case["presentation"]["comparison_groups"][0]["views"][0][
        "period"
    ] = '<script>alert("source")</script>'

    rendered = compile_html(build_plan(case, source_root=FIXTURE), source_root=FIXTURE)

    assert '<script>alert("source")</script>' not in rendered
    assert "&lt;script&gt;alert(&quot;source&quot;)&lt;/script&gt;" in rendered
    assert rendered.count("data-comparison-panel data-period=") == 2


@pytest.mark.parametrize(
    "problem, message",
    [
        ("missing", "monetary comparison"),
        ("duplicate", "Duplicate period"),
        ("assigned", "assigned more than once"),
        ("section", "one report section"),
        ("not_comparison", "monetary comparison"),
    ],
)
def test_ambiguous_or_unbound_views_reject_compilation(problem, message):
    case = interactive_case()
    views = case["presentation"]["comparison_groups"][0]["views"]
    if problem == "missing":
        views[0]["table_id"] = "missing"
    elif problem == "duplicate":
        views[1]["period"] = "Gennaio"
    elif problem == "assigned":
        views[1]["table_id"] = views[0]["table_id"]
    elif problem == "section":
        case["presentation"]["tables"][1]["section"] = "cash"
    else:
        del case["presentation"]["tables"][1]["comparison"]

    with pytest.raises(PlanningError, match=message):
        compile_html(build_plan(case, source_root=FIXTURE), source_root=FIXTURE)

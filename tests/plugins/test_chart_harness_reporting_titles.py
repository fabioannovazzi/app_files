from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHARED_VENDOR_ROOT = ROOT / "plugins" / "_shared" / "vendor"
if str(SHARED_VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_VENDOR_ROOT))

from modules.chart_harness import (  # noqa: E402
    reporting_entity_label_from_recipe,
    reporting_filter_label_from_recipe,
    reporting_subject_label_from_recipe,
    reporting_title_html,
)


def test_reporting_entity_label_prefers_explicit_recipe_label() -> None:
    recipe = {
        "source_file": "/tmp/hair_color_IV.xlsx",
        "options": {"reporting_entity_label": "Mexico hair color"},
    }

    label = reporting_entity_label_from_recipe(recipe)

    assert label == "Mexico hair color"


def test_reporting_entity_label_stays_plain_when_filters_are_active() -> None:
    recipe = {
        "source_file": "/tmp/hair_color_IV.xlsx",
        "options": {
            "reporting_entity_label": "Mexico hair color",
            "recipe_filter_audit": {
                "status": "written",
                "filters": [
                    {"column": "Company", "include": ["All Other Manufacturers"]}
                ],
            },
        },
    }

    label = reporting_entity_label_from_recipe(recipe)

    assert label == "Mexico hair color"


def test_reporting_filter_label_formats_include_filters() -> None:
    recipe = {
        "options": {
            "recipe_filter_audit": {
                "status": "written",
                "filters": [
                    {"column": "Company", "include": ["All Other Manufacturers"]}
                ],
            }
        },
    }

    label = reporting_filter_label_from_recipe(recipe)

    assert label == "Company = All Other Manufacturers"


def test_reporting_filter_label_formats_exclude_filters() -> None:
    recipe = {
        "options": {
            "recipe_filter_audit": {
                "status": "written",
                "filters": [{"column": "Company", "exclude": ["Competitor A"]}],
            }
        },
    }

    label = reporting_filter_label_from_recipe(recipe)

    assert label == "Company != Competitor A"


def test_reporting_subject_label_joins_entity_and_filter() -> None:
    recipe = {
        "source_file": "/tmp/hair_color_IV.xlsx",
        "options": {
            "reporting_entity_label": "Mexico hair color",
            "recipe_filter_audit": {
                "status": "written",
                "filters": [
                    {"column": "Company", "include": ["All Other Manufacturers"]}
                ],
            },
        },
    }

    label = reporting_subject_label_from_recipe(recipe)

    assert label == "Mexico hair color | Company = All Other Manufacturers"


def test_reporting_filter_label_falls_back_to_explicit_recipe_filters() -> None:
    recipe = {
        "options": {
            "recipe_filter_audit": {"status": "skipped"},
            "filters": {"Company": {"include": ["All Other Manufacturers"]}},
        },
    }

    label = reporting_filter_label_from_recipe(recipe)

    assert label == "Company = All Other Manufacturers"


def test_reporting_filter_label_limits_clauses_and_values() -> None:
    recipe = {
        "options": {
            "recipe_filter_audit": {
                "status": "written",
                "filters": [
                    {"column": "Company", "include": ["A", "B", "C", "D"]},
                    {"column": "Region", "exclude": ["North"]},
                    {"column": "Channel", "include": ["Retail"]},
                    {"column": "Brand", "include": ["Core"]},
                    {"column": "Type", "include": ["Permanent"]},
                ],
            }
        },
    }

    label = reporting_filter_label_from_recipe(recipe)

    assert label == (
        "Company = A, B, C; Region != North; Channel = Retail; Brand = Core"
    )


def test_reporting_filter_label_preserves_zero_values() -> None:
    recipe = {
        "options": {
            "recipe_filter_audit": {
                "status": "written",
                "filters": [{"column": "Rank", "include": [0]}],
            }
        },
    }

    label = reporting_filter_label_from_recipe(recipe)

    assert label == "Rank = 0"


def test_reporting_filter_label_formats_comparison_filters() -> None:
    recipe = {
        "options": {
            "recipe_filter_audit": {
                "status": "written",
                "filters": [{"column": "Value_LC", "gt": 0, "lte": 100}],
            }
        },
    }

    label = reporting_filter_label_from_recipe(recipe)

    assert label == "Value_LC > 0; Value_LC <= 100"


def test_reporting_filter_label_skips_hidden_title_filters() -> None:
    recipe = {
        "source_file": "/tmp/hair_color_IV.xlsx",
        "options": {
            "reporting_entity_label": "Mexico hair color",
            "recipe_filter_audit": {
                "status": "written",
                "filters": [
                    {"column": "Company", "include": ["All Other Manufacturers"]},
                    {
                        "column": "Date",
                        "include": ["2017-08-27"],
                        "display_in_title": False,
                    },
                    {
                        "column": "Value_LC",
                        "gt": 0,
                        "display_in_title": False,
                    },
                ],
            },
        },
    }

    label = reporting_subject_label_from_recipe(recipe)

    assert label == "Mexico hair color | Company = All Other Manufacturers"


def test_reporting_entity_label_falls_back_to_source_file_stem() -> None:
    recipe = {
        "source_file": "/tmp/hair_color_IV.xlsx",
        "options": {},
    }

    label = reporting_entity_label_from_recipe(recipe)

    assert label == "Hair Color"


def test_reporting_title_html_uses_standard_three_line_contract() -> None:
    title = reporting_title_html(
        "Mexico hair color",
        "<b>Sales</b> in mEUR by Brand",
        "YTD through 2017-08-27",
    )

    assert title == (
        "Mexico hair color"
        "<br><b>Sales</b> in mEUR by Brand"
        "<br>YTD through 2017-08-27"
    )

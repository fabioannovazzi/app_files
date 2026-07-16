from __future__ import annotations

from bs4 import BeautifulSoup  # type: ignore[import]

from src.slides.models import Slide
from src.slides.tagging import (
    EnrichedSlide,
    apply_enrichment_patch,
    stamp_slide,
    summarize_tagged_slides,
)


def _build_sample_slide_html() -> str:
    return """
    <html>
      <body>
        <div class="slide-container">
          <h1 class="slide-title">Revenue growth</h1>
          <div class="insight-card">
            <div class="metric" data-metric-unit="USD">120</div>
          </div>
          <div class="chart"><img src="chart.png" /></div>
          <h2>Next steps</h2>
          <ul>
            <li>Launch pricing floor</li>
          </ul>
          <aside class="slide-notes">note</aside>
          <footer class="slide-source">source</footer>
        </div>
      </body>
    </html>
    """


def test_stamp_slide_adds_expected_attributes_without_overwriting():
    slide = Slide(id="slide0.html", title_html="", body_html="", full_html=_build_sample_slide_html())
    stamped = stamp_slide(slide)

    soup = BeautifulSoup(stamped.html, "html.parser")
    container = soup.select_one(".slide-container")
    assert container is not None
    assert container["data-slide-id"] == "slide0.html"
    # Presence of the chart container should classify as an exhibit-kind slide
    assert container.get("data-slide-kind") == "exhibit"

    title = container.find("h1")
    assert title is not None
    assert title.get("data-block") == "title"

    metric = container.select_one('[data-block="metric"]')
    assert metric is not None
    assert metric.get("data-metric-unit") == "USD"  # preserved existing value
    assert metric.get("data-metric-label") == ""

    exhibit = container.select_one('[data-block="exhibit"]')
    assert exhibit is not None
    assert exhibit.get("data-source-ref") == "unknown"

    recommendation = container.select_one('[data-block="recommendation"]')
    assert recommendation is not None
    assert recommendation.get("data-priority") == "1"

    assert container.select_one('[data-block="notes"]')
    assert container.select_one('[data-block="sources"]')


def test_apply_enrichment_patch_sets_attributes_and_tracks_indexes():
    stamped = stamp_slide(
        Slide(id="slide0.html", title_html="", body_html="", full_html=_build_sample_slide_html())
    )
    patch = {
        "slide_topic": "pricing",
        "slide_kind": "insight",
        "metrics": [
            {
                "index": 0,
                "label": "Revenue 2024",
                "unit": "M USD",
                "year": "2024",
                "canonical_slide": "slide0.html",
            }
        ],
        "exhibits": [
            {"index": 0, "source_ref": "Company filings", "source_asof": "2023", "canonical_slide": "slide0.html"}
        ],
        "recommendations": [
            {
                "index": 0,
                "priority": "1",
                "owner": "Ops",
                "impact": "high",
                "relates_to": "slide0.html",
                "canonical_slide": "slide0.html",
            }
        ],
    }
    enriched = apply_enrichment_patch(stamped, patch)
    assert enriched.applied
    assert not enriched.issues

    soup = BeautifulSoup(enriched.html, "html.parser")
    container = soup.select_one(".slide-container")
    assert container is not None
    assert container.get("data-slide-topic") == "pricing"
    assert container.get("data-slide-kind") == "insight"

    metric = container.select('[data-block="metric"]')[0]
    assert metric.get("data-metric-label") == "Revenue 2024"
    assert metric.get("data-metric-unit") == "M USD"
    assert metric.get("data-metric-year") == "2024"
    assert metric.get("data-metric-canonical") == "slide0.html"

    exhibit = container.select('[data-block="exhibit"]')[0]
    assert exhibit.get("data-source-ref") == "Company filings"
    assert exhibit.get("data-source-asof") == "2023"
    assert exhibit.get("data-exhibit-canonical") == "slide0.html"

    recommendation = container.select('[data-block="recommendation"]')[0]
    assert recommendation.get("data-relates-to") == "slide0.html"
    assert recommendation.get("data-reco-canonical") == "slide0.html"
    assert recommendation.get("data-owner") == "Ops"
    assert recommendation.get("data-impact") == "high"


def test_summarize_tagged_slides_builds_index_and_clusters():
    enriched_primary = apply_enrichment_patch(
        stamp_slide(
            Slide(
                id="slide0.html",
                title_html="",
                body_html="",
                full_html=_build_sample_slide_html(),
            )
        ),
        {
            "metrics": [{"index": 0, "canonical_slide": "slide0.html"}],
            "recommendations": [{"index": 0, "canonical_slide": "slide0.html"}],
        },
    )
    duplicate_html = """
    <div class="slide-container" data-slide-kind="insight">
      <div data-block="metric" data-metric-canonical="slide0.html"></div>
      <ul data-block="recommendations">
        <li data-block="recommendation"></li>
      </ul>
    </div>
    """
    enriched_duplicate = EnrichedSlide(
        slide_id="slide1.html",
        html=duplicate_html,
        applied=True,
        issues=[],
    )

    summary = summarize_tagged_slides([enriched_primary, enriched_duplicate])

    assert len(summary.index) == 2
    assert summary.metric_duplicates.get("slide0.html") == ["slide0.html", "slide1.html"]
    assert summary.recommendation_duplicates.get("slide0.html") == ["slide0.html"]
    assert "slide1.html" in summary.missing_recommendation_links

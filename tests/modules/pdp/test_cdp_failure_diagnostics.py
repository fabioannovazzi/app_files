from __future__ import annotations

from modules.pdp.cdp_failure_diagnostics import classify_cdp_failure


def test_classify_cdp_failure_detects_kpsdk_challenge_shell() -> None:
    html = """
    <!DOCTYPE html>
    <html>
      <body>
        <script>window.KPSDK = {};</script>
        <script src="/challenge/ips.js?KP_UIDz=abc"></script>
      </body>
    </html>
    """

    diagnosis = classify_cdp_failure(
        requested_url="https://www.chewy.com/b/wet-food-389?sort=newest",
        final_url="https://www.chewy.com/b/wet-food-389?sort=newest",
        page_title="",
        html=html,
        selector="a[href]",
        reason="no_candidates",
        retailer="chewy",
        category_key="wet_cat_food",
        candidate_count=0,
        selector_found=False,
    )

    assert diagnosis["classification"] == "kasada_kpsdk_challenge"
    assert "KPSDK challenge shell" in str(diagnosis["suggested_action"])

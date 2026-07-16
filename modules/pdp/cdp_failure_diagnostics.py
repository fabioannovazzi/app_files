from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup  # type: ignore[import]

__all__ = [
    "classify_cdp_failure",
    "write_cdp_failure_bundle",
]

_CLOUDFLARE_TERMS = (
    "just a moment",
    "cloudflare",
    "turnstile",
    "checking your browser",
    "verify you are human",
    "cdn-cgi/challenge-platform",
)
_KASADA_KPSDK_TERMS = (
    "kpsdk",
    "kp_uidz",
    "ips.js",
    "x-kpsdk",
)
_LOGIN_TERMS = (
    "sign in",
    "log in",
    "login",
    "password",
    "email address",
    "account",
)
_ERROR_TERMS = (
    "access denied",
    "forbidden",
    "not found",
    "temporarily unavailable",
    "service unavailable",
    "error",
)
_PROMO_TERMS = (
    "sign up",
    "join now",
    "rewards",
    "bonus event",
    "subscribe",
    "newsletter",
)


def classify_cdp_failure(
    *,
    requested_url: str,
    final_url: str,
    page_title: str | None,
    html: str,
    selector: str,
    reason: str,
    retailer: str,
    category_key: str | None,
    candidate_count: int,
    selector_found: bool,
) -> dict[str, object]:
    """Return a structured diagnosis for one failed CDP capture."""

    soup = BeautifulSoup(html or "", "lxml")
    try:
        selector_match_count = len(soup.select(selector)) if selector else 0
    except Exception:
        selector_match_count = 0

    body_text = " ".join(soup.get_text(" ", strip=True).split())
    body_lower = body_text.lower()
    title = str(page_title or "").strip()
    title_lower = title.lower()
    final_url_lower = str(final_url or "").strip().lower()
    html_lower = str(html or "").lower()

    product_tile_count = len(soup.select("div.product_tile[data-itemid]"))
    product_link_hint_count = len(
        soup.select(
            "a[href$='.html'], "
            "a[href*='.html?'], "
            "a[href*='/dp/'], "
            "a[href*='/gp/product/'], "
            "a[href*='/p/']"
        )
    )
    dialog_count = len(
        soup.select("dialog, [role='dialog'], [aria-modal='true'], .modal, .popup")
    )
    password_input_count = len(soup.select("input[type='password']"))

    classification = "unknown"
    suggested_action = (
        "Inspect the saved screenshot and HTML snapshot to determine the next fix."
    )

    if any(term in html_lower for term in _KASADA_KPSDK_TERMS):
        classification = "kasada_kpsdk_challenge"
        suggested_action = (
            "Use a browser profile that already renders this retailer, or switch "
            "to a retailer-specific acquisition/API path; the saved page is only "
            "a KPSDK challenge shell and contains no listing products."
        )
    elif (
        any(
            term in title_lower or term in body_lower or term in html_lower
            for term in _CLOUDFLARE_TERMS
        )
        or "cdn-cgi/challenge-platform" in final_url_lower
    ):
        classification = "cloudflare_challenge"
        suggested_action = (
            "Use a visible browser session or cleaner proxy/IP and clear the "
            "challenge in the attached Chrome profile."
        )
    elif (
        "access to this page has been denied" in body_lower
        or "security check" in body_lower
    ):
        classification = "access_denied_interstitial"
        suggested_action = (
            "Clear the human verification in the attached browser session, then rerun "
            "or resume the crawl."
        )
    elif any(term in title_lower or term in body_lower for term in _ERROR_TERMS):
        classification = "empty_or_error_page"
        suggested_action = (
            "Verify the target URL and retailer availability; the saved page is "
            "an error or access-denied response rather than a listing."
        )
    elif (
        password_input_count > 0
        or sum(term in body_lower for term in _LOGIN_TERMS) >= 2
    ):
        classification = "login_gate"
        suggested_action = (
            "Authenticate in the attached browser profile, then rerun the crawl."
        )
    elif dialog_count > 0 and any(term in body_lower for term in _PROMO_TERMS):
        classification = "modal_or_popup_blocking"
        suggested_action = (
            "Dismiss the blocking modal in the visible browser or add retailer-"
            "specific dismissal logic for this popup."
        )
    elif candidate_count == 0 and (
        product_tile_count > 0
        or product_link_hint_count > 0
        or selector_match_count > 0
    ):
        classification = "selector_mismatch_or_dom_change"
        suggested_action = (
            "The page appears to contain product-like elements, so inspect the "
            "saved HTML and update the retailer selector or link canonicalization."
        )
    elif reason == "navigation_failed":
        classification = "navigation_failed"
        suggested_action = (
            "Check Chrome CDP reachability and whether the attached browser tab "
            "is still alive and loading the requested URL."
        )
    elif candidate_count == 0:
        classification = "no_products_detected"
        suggested_action = (
            "Inspect the saved page state; the listing rendered without detectable "
            "PDP links."
        )

    return {
        "classification": classification,
        "suggested_action": suggested_action,
        "retailer": retailer,
        "category_key": category_key,
        "reason": reason,
        "requested_url": requested_url,
        "final_url": final_url,
        "page_title": title,
        "selector": selector,
        "candidate_count": candidate_count,
        "selector_found": selector_found,
        "signals": {
            "selector_match_count": selector_match_count,
            "product_tile_count": product_tile_count,
            "product_link_hint_count": product_link_hint_count,
            "dialog_count": dialog_count,
            "password_input_count": password_input_count,
        },
        "body_excerpt": body_text[:1200],
    }


def write_cdp_failure_bundle(
    *,
    artifact_root: Path,
    requested_url: str,
    final_url: str,
    page_title: str | None,
    html: str,
    selector: str,
    reason: str,
    retailer: str,
    category_key: str | None,
    candidate_count: int,
    selector_found: bool,
    screenshot_png: bytes | None = None,
) -> Path:
    """Persist screenshot, HTML, and diagnosis for one failed page capture."""

    artifact_root.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe_category = _slugify(category_key or "unknown-category")
    safe_reason = _slugify(reason)
    bundle_stem = f"{timestamp}_{safe_category}_{safe_reason}"
    bundle_dir = artifact_root / bundle_stem
    bundle_dir.mkdir(parents=True, exist_ok=True)

    html_path = bundle_dir / "page.html"
    html_path.write_text(html or "", encoding="utf-8")

    screenshot_path: str | None = None
    if screenshot_png:
        image_path = bundle_dir / "page.png"
        image_path.write_bytes(screenshot_png)
        screenshot_path = str(image_path)

    diagnosis = classify_cdp_failure(
        requested_url=requested_url,
        final_url=final_url,
        page_title=page_title,
        html=html,
        selector=selector,
        reason=reason,
        retailer=retailer,
        category_key=category_key,
        candidate_count=candidate_count,
        selector_found=selector_found,
    )
    diagnosis["html_path"] = str(html_path)
    diagnosis["screenshot_path"] = screenshot_path

    (bundle_dir / "diagnosis.json").write_text(
        json.dumps(diagnosis, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return bundle_dir


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip().lower())
    return cleaned.strip("-") or "unknown"

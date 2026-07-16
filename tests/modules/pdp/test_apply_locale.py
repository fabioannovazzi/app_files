from __future__ import annotations

from modules.pdp.profile_loader import load_profile
from modules.pdp.service import apply_locale


def test_apply_locale_replaces_placeholder_in_category_urls() -> None:
    profile = load_profile("kiko_lipstick")

    localized = apply_locale(profile, "fr-fr")

    assert all("/fr-fr/" in url for url in localized.category_urls)
    # other fields should remain unchanged
    assert localized.retailer == profile.retailer

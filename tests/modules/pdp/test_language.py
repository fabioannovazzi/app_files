from __future__ import annotations

from typing import Any, Dict, Optional

import pytest
from starlette.requests import Request

from modules.pdp.language import (
    LANDING_LANGUAGE_LABELS,
    get_navigation_label,
    get_page_copy,
    resolve_language,
)


async def _empty_receive() -> Dict[str, Any]:
    return {"type": "http.request", "body": b"", "more_body": False}


def _build_request(
    query: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    cookies: Optional[Dict[str, str]] = None,
) -> Request:
    raw_headers = []
    headers = headers or {}
    for key, value in headers.items():
        raw_headers.append((key.lower().encode("latin-1"), value.encode("latin-1")))
    if cookies:
        cookie_header = "; ".join(f"{key}={value}" for key, value in cookies.items())
        raw_headers.append((b"cookie", cookie_header.encode("latin-1")))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": (query or "").encode("latin-1"),
        "headers": raw_headers,
        "client": ("203.0.113.5", 12345),
    }
    return Request(scope, _empty_receive)


def test_resolve_language_prefers_query_params_over_cookie_and_header() -> None:
    request = _build_request(
        query="lang=fr",
        headers={"accept-language": "it-IT,it;q=0.9,en;q=0.8"},
        cookies={"lang": "de"},
    )
    assert resolve_language(request) == "fr"


def test_resolve_language_uses_cookie_when_query_missing() -> None:
    request = _build_request(cookies={"lang": "de"})
    assert resolve_language(request) == "de"


def test_resolve_language_falls_back_to_accept_language_header() -> None:
    request = _build_request(headers={"accept-language": "it-IT,it;q=0.9,en;q=0.8"})
    assert resolve_language(request) == "it"


def test_resolve_language_defaults_to_english() -> None:
    request = _build_request()
    assert resolve_language(request) == "en"


def test_landing_language_labels_use_short_locale_codes() -> None:
    assert LANDING_LANGUAGE_LABELS == {
        "en": "En",
        "it": "It",
        "fr": "Fr",
        "de": "De",
    }


def test_get_navigation_label_returns_locale_specific_text() -> None:
    assert (
        get_navigation_label("it", "/check/page") == "Verifica registrazioni contabili"
    )


def test_get_navigation_label_handles_presentations_page() -> None:
    assert get_navigation_label("de", "/presentations/page") == "Präsentationen"


def test_get_navigation_label_uses_updated_attribute_analysis_labels() -> None:
    assert get_navigation_label("en", "/review/reports/page") == "Retailer signals"
    assert get_navigation_label("en", "/review/brand-reports/page") == "Brand fit"
    assert (
        get_navigation_label("en", "/review/product-hypotheses/page") == "Product hints"
    )
    assert (
        get_navigation_label("it", "/review/product-hypotheses/page")
        == "Spunti prodotto"
    )
    assert (
        get_navigation_label("fr", "/review/product-hypotheses/page")
        == "Pistes produit"
    )
    assert (
        get_navigation_label("de", "/review/product-hypotheses/page")
        == "Produkt-Hinweise"
    )


def test_get_navigation_label_falls_back_to_english() -> None:
    assert get_navigation_label("es", "/check/page") == "Check entries"


def test_get_page_copy_returns_nested_translations() -> None:
    copy = get_page_copy("check_statements", "it")
    assert copy["panels"]["upload"]["title"] == "Carica i file"
    assert copy["labels"]["bank_files"] == "Estratti conto bancari"
    review_copy = get_page_copy("product_attributes", "fr")
    assert review_copy["labels"]["brand"] == "Marque"
    assert review_copy["panels"]["results"]["download_csv"] == "Télécharger le CSV"
    presentations_copy = get_page_copy("presentations", "fr")
    assert presentations_copy["form"]["button"] == "Continuer"


@pytest.mark.parametrize(
    (
        "lang",
        "expected_primary_navigation",
        "expected_language_selector",
        "expected_sign_out",
    ),
    (
        ("en", "Primary navigation", "Language selector", "Sign out"),
        ("it", "Navigazione principale", "Selezione della lingua", "Esci"),
        ("fr", "Navigation principale", "Sélecteur de langue", "Se déconnecter"),
        ("de", "Hauptnavigation", "Sprachauswahl", "Abmelden"),
    ),
)
def test_get_page_copy_localizes_landing_header_controls(
    lang: str,
    expected_primary_navigation: str,
    expected_language_selector: str,
    expected_sign_out: str,
) -> None:
    copy = get_page_copy("landing", lang)

    assert copy["primary_navigation_label"] == expected_primary_navigation
    assert copy["language_selector_label"] == expected_language_selector
    assert copy["sign_out_button"] == expected_sign_out


@pytest.mark.parametrize(
    ("lang", "key", "expected_copy"),
    (
        (
            "fr",
            "magic_link_tooltip",
            "Saisissez votre adresse e-mail : nous vous enverrons un lien de connexion "
            "à usage unique.",
        ),
        (
            "de",
            "magic_link_invalid_email",
            "Geben Sie eine gültige E-Mail-Adresse ein.",
        ),
        (
            "de",
            "magic_link_sent",
            "Prüfen Sie Ihren Posteingang: Der Anmeldelink bleibt 15 Minuten gültig. "
            "Wenn Sie ihn nicht sehen, prüfen Sie auch den Spam- oder Junk-Ordner.",
        ),
    ),
)
def test_get_page_copy_preserves_native_landing_auth_spelling(
    lang: str,
    key: str,
    expected_copy: str,
) -> None:
    copy = get_page_copy("landing", lang)

    assert copy[key] == expected_copy


def test_get_page_copy_unknown_page_returns_empty_dict() -> None:
    assert get_page_copy("missing_page", "en") == {}


def test_get_page_copy_handles_slides_editor_export_labels() -> None:
    copy = get_page_copy("slides_editor", "it")

    assert copy["labels"]["save_deck"] == "Salva deck"
    assert copy["labels"]["print_deck"] == "Esporta PDF"
    assert copy["labels"]["export_pptx"] == "Esporta PPTX"

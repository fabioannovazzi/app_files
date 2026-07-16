from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping, Sequence

from requests import HTTPError, Response

from .adapters import NullAdapter, RetailerAdapter
from .blob_extractors import extract_primary_blobs
from .brand_identity import (
    infer_brand_from_product_context,
    product_context_summary,
    should_replace_brand,
)
from .fetcher import HTMLFetcher
from .json_path import extract_values
from .models import (
    BatchParseResult,
    EvidenceBlob,
    FetchResult,
    ParentProduct,
    ParseResult,
    RawEvidence,
    Variant,
)
from .normalization import normalize_text
from .profile import ParentRules, PDPProfile
from .storage import EvidenceStorage
from .validation import validate_parent_and_variants


def _coerce_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _collect_strings(value: object) -> list[str]:
    results: list[str] = []
    if isinstance(value, str):
        text = value.strip()
        if text:
            results.append(text)
    elif isinstance(value, (int, float)):
        results.append(str(value))
    elif isinstance(value, Sequence):
        for item in value:
            results.extend(_collect_strings(item))
    return results


def _parse_decimal(value: object) -> tuple[Decimal | None, bool]:
    if value is None:
        return None, True
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)), True
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None, True
        sanitized = text.replace("$", "").replace(",", "")
        try:
            return Decimal(sanitized), True
        except InvalidOperation:
            return None, False
    return None, False


def _flatten_variant_objects(values: Sequence[object]) -> list[Mapping[str, object]]:
    variants: list[Mapping[str, object]] = []
    for value in values:
        if isinstance(value, Mapping):
            variants.append(value)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for item in value:
                if isinstance(item, Mapping):
                    variants.append(item)
    return variants


def _extract_first_from_payload(
    payload: object,
    expressions: Sequence[str],
) -> str | None:
    for expression in expressions:
        for value in extract_values(payload, expression):
            text = _coerce_string(value)
            if text:
                return text
    return None


def _extract_all_from_payload(
    payload: object,
    expressions: Sequence[str],
) -> list[str]:
    collected: list[str] = []
    for expression in expressions:
        for value in extract_values(payload, expression):
            collected.extend(_collect_strings(value))
    return collected


def _has_color_selector(
    variants: Sequence[Variant],
    parent_title: str | None,
    parent_rules: ParentRules,
) -> bool:
    has_shade_names = any(variant.shade_name_raw for variant in variants)
    meets_threshold = (
        len(variants) >= parent_rules.min_color_variants and has_shade_names
    )
    if not meets_threshold:
        return False
    if parent_rules.disallow_kits_pattern and parent_title:
        if parent_rules.disallow_kits_pattern.search(parent_title):
            return False
    return True


@dataclass(slots=True)
class ParserComponents:
    profile: PDPProfile
    adapter: RetailerAdapter
    fetcher: HTMLFetcher | None
    storage: EvidenceStorage | None


class FetchError(RuntimeError):
    """Wrap HTTP errors raised while fetching PDP pages."""

    def __init__(
        self,
        *,
        url: str,
        status_code: int | None,
        explanation: str | None,
        original_exception: HTTPError | None,
    ) -> None:
        detail = f" (status={status_code})"
        if explanation:
            detail += f": {explanation}"
        message = f"Failed to fetch {url}{detail}"
        super().__init__(message)
        self.url = url
        self.status_code = status_code
        self.explanation = explanation
        self.original_exception = original_exception


class PDPParser:
    """Config-driven parser for retailer PDP pages."""

    def __init__(
        self,
        profile: PDPProfile,
        *,
        adapter: RetailerAdapter | None = None,
        fetcher: HTMLFetcher | None = None,
        storage: EvidenceStorage | None = None,
    ) -> None:
        self.profile = profile
        self.adapter = adapter or NullAdapter()
        self.fetcher = fetcher
        self.storage = storage

    def parse_url(
        self,
        url: str,
        *,
        html: str | None = None,
        timeout: float | tuple[float, float] = 20.0,
    ) -> ParseResult:
        fetch_result = self._ensure_fetch_result(url, html=html, timeout=timeout)
        blobs = list(extract_primary_blobs(fetch_result.html, self.profile))
        extra = list(self.adapter.extra_blobs(fetch_result.html))
        blobs.extend(extra)

        parent, variants, parse_errors, parse_warnings = self._parse_from_blobs(
            url, fetch_result, blobs
        )

        raw_evidence = RawEvidence()
        if self.storage and parent and parent.parent_product_id:
            try:
                raw_evidence = self.storage.persist(
                    retailer=self.profile.retailer,
                    parent_product_id=parent.parent_product_id,
                    fetch_result=fetch_result,
                    blobs=blobs,
                )
            except Exception as exc:
                parse_warnings = tuple(list(parse_warnings) + [f"storage_error:{exc}"])

        return ParseResult(
            parent=parent,
            variants=tuple(variants),
            fetch_result=fetch_result,
            blobs=tuple(blobs),
            raw_evidence=raw_evidence,
            errors=parse_errors,
            warnings=parse_warnings,
        )

    def parse_urls(self, urls: Sequence[str]) -> BatchParseResult:
        results: list[ParseResult] = []
        failures: list[str] = []
        for url in urls:
            try:
                results.append(self.parse_url(url))
            except FetchError as fetch_error:
                status_text = f"http_status={fetch_error.status_code}"
                extra = (
                    f"; {fetch_error.explanation}" if fetch_error.explanation else ""
                )
                details = f"{url} ({status_text}{extra})"
                failures.append(details)
            except Exception:
                failures.append(url)
        return BatchParseResult(
            retailer=self.profile.retailer,
            profile_name=self.profile.profile_name,
            parsed=tuple(results),
            failures=tuple(failures),
            generated_at=dt.datetime.now(dt.timezone.utc),
        )

    def _ensure_fetch_result(
        self,
        url: str,
        *,
        html: str | None = None,
        timeout: float | tuple[float, float] = 20.0,
    ) -> FetchResult:
        if html is not None:
            fetched_at = dt.datetime.now(dt.timezone.utc)
            return FetchResult(
                url=url, status_code=200, headers={}, html=html, fetched_at=fetched_at
            )
        if not self.fetcher:
            raise RuntimeError("HTMLFetcher not configured for network fetches.")
        try:
            return self.fetcher.fetch(url, timeout=timeout)
        except HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            explanation = None
            if exc.response is not None:
                explanation = _summarize_http_error(exc.response)
            raise FetchError(
                url=url,
                status_code=status_code,
                explanation=explanation,
                original_exception=exc,
            ) from exc

    def _parse_from_blobs(
        self,
        url: str,
        fetch_result: FetchResult,
        blobs: Sequence[EvidenceBlob],
    ) -> tuple[ParentProduct | None, list[Variant], tuple[str, ...], tuple[str, ...]]:
        errors: list[str] = []
        warnings: list[str] = []

        payloads: list[tuple[int, object]] = [
            (blob.index, blob.payload) for blob in blobs if blob.payload is not None
        ]

        parent_id = self.adapter.primary_id_from_url(url)
        profile = self.profile

        if not parent_id:
            for index, payload in payloads:
                parent_id = _extract_first_from_payload(
                    payload, profile.id_extractors.parent_json_paths
                )
                if parent_id:
                    break

        if not parent_id:
            errors.append("missing_parent_id")
            return None, [], tuple(errors), tuple(warnings)

        brand_raw = None
        title_raw = None
        series_label_raw = None
        parent_summary_raw = None
        category_values: list[str] = []

        for index, payload in payloads:
            if not brand_raw:
                brand_raw = _extract_first_from_payload(
                    payload, profile.field_paths.brand
                )
            if not title_raw:
                title_raw = _extract_first_from_payload(
                    payload, profile.field_paths.parent_title
                )
            if not series_label_raw:
                series_label_raw = _extract_first_from_payload(
                    payload, profile.field_paths.series_label
                )
            if parent_summary_raw is None and profile.field_paths.parent_summary:
                parent_summary_raw = _extract_first_from_payload(
                    payload, profile.field_paths.parent_summary
                )
            if not category_values:
                category_values = _extract_all_from_payload(
                    payload, profile.field_paths.category_path
                )

        seen_categories: set[str] = set()
        category_path: list[str] = []
        for category in category_values:
            if category not in seen_categories:
                category_path.append(category)
                seen_categories.add(category)

        variant_order: list[str] = []
        variant_payloads: dict[str, dict[str, object]] = {}
        variant_source_index: dict[str, int] = {}
        variant_id_paths = profile.field_paths.variant_fields.get("variant_id", ())

        for index, payload in payloads:
            for expression in profile.field_paths.variant_list:
                values = extract_values(payload, expression)
                flattened = _flatten_variant_objects(values)
                for raw_variant in flattened:
                    variant_id = _extract_first_from_payload(
                        raw_variant, variant_id_paths
                    )
                    if not variant_id:
                        continue
                    existing = variant_payloads.get(variant_id)
                    if existing is None:
                        variant_payloads[variant_id] = dict(raw_variant)
                        variant_order.append(variant_id)
                        variant_source_index[variant_id] = index
                    else:
                        merged = dict(existing)
                        for key, value in raw_variant.items():
                            if key not in merged or merged[key] in (None, "", [], {}):
                                merged[key] = value
                        variant_payloads[variant_id] = merged

        variants: list[Variant] = []
        skipped_variants = 0
        variant_fields = profile.field_paths.variant_fields

        for position, variant_id in enumerate(variant_order):
            variant_payload = variant_payloads.get(variant_id)
            if not variant_payload:
                continue

            variant_id = _extract_first_from_payload(variant_payload, variant_id_paths)
            if not variant_id:
                skipped_variants += 1
                continue

            shade_raw = _extract_first_from_payload(
                variant_payload, variant_fields.get("shade_name", ())
            )
            size_text = _extract_first_from_payload(
                variant_payload, variant_fields.get("size_text", ())
            )
            price_raw = _extract_first_from_payload(
                variant_payload, variant_fields.get("price", ())
            )
            currency = _extract_first_from_payload(
                variant_payload, variant_fields.get("currency", ())
            )
            barcode = _extract_first_from_payload(
                variant_payload, variant_fields.get("barcode", ())
            )
            swatch_url = _extract_first_from_payload(
                variant_payload, variant_fields.get("swatch_image", ())
            )
            hero_url = _extract_first_from_payload(
                variant_payload, variant_fields.get("hero_image", ())
            )
            availability = _extract_first_from_payload(
                variant_payload, variant_fields.get("availability", ())
            )

            parsed_price, price_ok = _parse_decimal(price_raw)
            variant_flags: list[str] = []
            if price_raw and not price_ok and profile.validation.price_must_be_numeric:
                variant_flags.append("price_not_numeric")

            shade_normalized = normalize_text(
                shade_raw, profile.normalization.shade_name
            )

            extras: dict[str, object] = {}
            shade_description = variant_payload.get("shadeDescription")
            if isinstance(shade_description, str) and shade_description:
                extras["shade_description"] = shade_description
            attributes = variant_payload.get("attributes")
            if isinstance(attributes, Mapping) and attributes:
                extras["attributes"] = dict(attributes)
            badges = variant_payload.get("badges")
            if isinstance(badges, Sequence) and badges:
                extras["badges"] = [
                    str(item) for item in badges if isinstance(item, str)
                ]
            promotion_tags = variant_payload.get("promotionTags")
            if isinstance(promotion_tags, Sequence) and promotion_tags:
                extras["promotion_tags"] = [
                    str(item) for item in promotion_tags if isinstance(item, str)
                ]
            variant_label = variant_payload.get("variantLabel")
            if isinstance(variant_label, str) and variant_label:
                extras["variant_label"] = variant_label

            list_price = _extract_first_from_payload(
                variant_payload, variant_fields.get("list_price", ())
            )
            if list_price:
                extras["list_price"] = list_price
            if list_price and not price_raw:
                price_raw = list_price

            variants.append(
                Variant(
                    retailer=profile.retailer,
                    parent_product_id=parent_id,
                    variant_id=variant_id,
                    shade_name_raw=shade_raw,
                    shade_name_normalized=shade_normalized,
                    size_text_raw=size_text,
                    price_raw=price_raw,
                    price=parsed_price,
                    currency=currency,
                    barcode=barcode,
                    swatch_image_url=swatch_url,
                    hero_image_url=hero_url,
                    availability=availability,
                    source_index=variant_source_index.get(variant_id),
                    qa_flags=tuple(variant_flags),
                    extras=extras,
                )
            )

        if skipped_variants:
            warnings.append(f"variants_without_ids:{skipped_variants}")

        brand_normalized = normalize_text(brand_raw, profile.normalization.brand)
        title_normalized = normalize_text(title_raw, profile.normalization.title)

        has_color_selector = _has_color_selector(
            variants, title_raw, profile.parent_rules
        )

        parent = ParentProduct(
            retailer=profile.retailer,
            parent_product_id=parent_id,
            pdp_url=url,
            brand_raw=brand_raw or "",
            brand_normalized=brand_normalized,
            title_raw=title_raw or "",
            title_normalized=title_normalized,
            series_label_raw=series_label_raw,
            category_path=tuple(category_path),
            has_color_selector=has_color_selector,
        )

        if parent_summary_raw:
            parent.extras["summary"] = parent_summary_raw

        self.adapter.retailer_specific_fixes(
            parent, variants, profile_name=profile.profile_name
        )
        self._apply_product_identity_brand_guard(parent)

        parent.has_color_selector = _has_color_selector(
            variants, parent.title_raw, profile.parent_rules
        )

        validation_errors, validation_warnings = validate_parent_and_variants(
            parent, variants, profile
        )
        errors.extend(validation_errors)
        warnings.extend(validation_warnings)

        return parent, variants, tuple(errors), tuple(warnings)

    @staticmethod
    def _apply_product_identity_brand_guard(parent: ParentProduct) -> None:
        summary = product_context_summary(dict(parent.extras))
        inferred_brand = infer_brand_from_product_context(
            product_url=parent.pdp_url,
            title=parent.title_raw,
            summary=summary,
        )
        if not should_replace_brand(
            parent.brand_raw,
            inferred_brand,
            product_url=parent.pdp_url,
            title=parent.title_raw,
            summary=summary,
        ):
            return
        parent.brand_raw = inferred_brand or parent.brand_raw
        parent.brand_normalized = inferred_brand or parent.brand_normalized
        if "brand_guard_context_override" not in parent.qa_flags:
            parent.qa_flags = (*parent.qa_flags, "brand_guard_context_override")


def _summarize_http_error(response: Response) -> str | None:
    reason = (response.reason or "").strip()
    snippet = response.text
    if not snippet and response.content:
        try:
            snippet = response.content.decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - fallback decode path
            snippet = ""
    snippet = (snippet or "").strip()
    if snippet:
        snippet = " ".join(snippet.split())
        max_len = 400
        if len(snippet) > max_len:
            snippet = f"{snippet[:max_len]}..."
    parts: list[str] = []
    if reason:
        parts.append(reason)
    if snippet:
        parts.append(f"body_snippet={snippet}")
    summary = "; ".join(parts)
    return summary or None


__all__ = ["FetchError", "PDPParser"]

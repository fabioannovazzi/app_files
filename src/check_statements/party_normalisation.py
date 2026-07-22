from __future__ import annotations

"""Helpers to extract and normalise counterparty names consistently."""

import re
import unicodedata
from typing import Any, Iterable

from src.check_statements.models import Transaction

__all__ = (
    "_trim_party_markers",
    "_normalize_party_local",
    "_clean_party_for_evidence",
    "_preferred_bank_party",
    "_preferred_ledger_party",
    "_ledger_payroll_text",
)


_LEADING_MARKER_PATTERN = re.compile(
    r"(?i)^\s*\b(?:n\.?|num(?:ero)?\.?|id|fatt(?:ura)?|rif\.?|trn|cro|iban|doc)\b[\s:#-]*[0-9A-Z./-]*",
)
_TRAILING_MARKER_PATTERN = re.compile(
    r"(?i)(?:[-,:; ]+)?\b(?:n\.?|num(?:ero)?\.?|id|fatt(?:ura)?|rif\.?|trn|cro|iban|doc)\b.*$",
)
_CURRENCY_PATTERN = re.compile(r"(?i)\b(?:eur|euro|usd|gbp|chf|aud|cad)\b")
_GENERIC_LEDGER_LABELS = {
    "PAGAMENTI",
    "PAGAMENTO",
    "PAGAMENTI VARI",
    "PAGAMENTI DIVERSI",
    "PAGAMENTO VARI",
    "PAGAMENTO DIVERSI",
    "GIROCONTI",
    "GIROCONTO",
    "VARI",
    "DOCUMENTO",
    "VARIE",
    "PAGOS",
    "PAGO",
    "PAGOS VARIOS",
    "MOVIMIENTOS VARIOS",
}

_LEDGER_PAYROLL_KEYS = (
    "counter_account_desc",
    "extra_desc",
    "details",
    "narrative",
    "causale_desc",
    "movement_desc",
    "memo",
    "account_name",
    "account_desc",
)

_LANG_NOISE = {
    "it": {
        "leading": {
            "pagamenti",
            "pagamento",
            "vari",
            "varie",
            "vario",
            "diversi",
            "diverse",
            "diverso",
            "bonifico",
            "bonifici",
            "bonificooc",
            "oc",
            "disposizione",
            "istantaneo",
            "pagata",
            "pagate",
            "pag",
            "ftt",
            "comm",
            "commissione",
            "commissioni",
            "causale",
            "giroconto",
            "giro",
            "operazione",
            "operazioni",
            "movimento",
            "movimenti",
            "prelievo",
            "prelievi",
            "versamento",
            "versamenti",
            "accredito",
            "addebito",
            "addebiti",
            "sdd",
            "rid",
            "revoca",
            "storno",
            "favore",
            "per",
            "intestato",
            "rilevazioni",
            "vers",
            "socio",
        },
        "noise": {
            "banca",
            "bank",
            "conto",
            "conti",
            "contabile",
            "contabili",
            "codice",
            "cod",
            "iban",
            "swift",
            "caus",
            "causali",
            "doc",
            "documento",
            "documenti",
            "nr",
            "num",
            "numero",
            "c/c",
            "cc",
            "sepa",
            "sdn",
            "det",
            "dettagli",
            "descrizione",
            "descrizioni",
            "descr",
            "ref",
            "rif",
            "riferimento",
            "riferimenti",
            "abi",
            "cab",
            "vers",
            "oc",
            "pagto",
        },
        "bank": {
            "banca",
            "bank",
            "bper",
            "unicredit",
            "postepay",
            "poste",
            "post",
            "bpm",
            "bnl",
            "bnp",
            "mps",
            "credem",
            "sella",
            "sparkasse",
            "ing",
            "fineco",
            "mediolanum",
            "chebanca",
            "revolut",
            "n26",
            "wise",
            "santander",
            "ubs",
            "barclays",
            "credit",
            "credito",
            "popolare",
            "popolari",
            "cassa",
            "risparmio",
        },
    },
    "en": {
        "leading": {
            "payment",
            "payments",
            "transfer",
            "transfers",
            "instant",
            "bank",
            "credit",
            "debit",
            "fee",
            "charge",
            "charges",
            "commission",
            "commissions",
            "reference",
            "ref",
            "ref.",
            "details",
            "detail",
            "memo",
            "note",
        },
        "noise": {
            "bank",
            "account",
            "acct",
            "acc",
            "number",
            "no",
            "ref",
            "reference",
            "swift",
            "iban",
            "currency",
            "eur",
            "usd",
            "gbp",
            "charge",
            "charges",
            "fee",
            "fees",
            "memo",
            "note",
        },
        "bank": {
            "bank",
            "hsbc",
            "barclays",
            "lloyds",
            "santander",
            "citi",
            "citibank",
            "boa",
            "chase",
            "natwest",
            "monzo",
            "revolut",
            "wise",
        },
    },
    "fr": {
        "leading": {
            "virement",
            "paiement",
            "paiements",
            "transfert",
            "versement",
            "versements",
            "prélèvement",
            "prelevement",
            "commission",
            "commissions",
            "référence",
            "reference",
            "réf",
            "ref",
            "détail",
            "details",
            "note",
        },
        "noise": {
            "banque",
            "compte",
            "compte",
            "numero",
            "num",
            "référence",
            "reference",
            "rib",
            "iban",
            "swift",
            "commission",
            "commissions",
            "monnaie",
            "eur",
        },
        "bank": {
            "banque",
            "bnp",
            "societe",
            "générale",
            "generale",
            "credit",
            "mutuel",
            "caisse",
            "epargne",
            "lcl",
            "hsbc",
            "axa",
            "hellobank",
        },
    },
    "es": {
        "leading": {
            "pago",
            "pagos",
            "transferencia",
            "transferencias",
            "traspaso",
            "ingreso",
            "adeudo",
            "abono",
            "domiciliacion",
            "domiciliado",
            "sepa",
            "instantanea",
            "instantaneo",
            "comision",
            "comisiones",
            "concepto",
            "referencia",
            "ref",
            "detalle",
            "operacion",
            "movimiento",
            "retirada",
            "reintegro",
        },
        "noise": {
            "banco",
            "banca",
            "cuenta",
            "numero",
            "nro",
            "referencia",
            "ref",
            "iban",
            "swift",
            "moneda",
            "eur",
            "concepto",
            "descripcion",
            "detalle",
            "sepa",
        },
        "bank": {
            "banco",
            "banca",
            "santander",
            "bbva",
            "caixabank",
            "caixa",
            "sabadell",
            "bankinter",
            "unicaja",
            "iberacaja",
            "kutxabank",
            "abanca",
            "openbank",
            "ing",
            "revolut",
            "wise",
        },
    },
}

_DEFAULT_LANG = "it"


def _normalise_lang(lang: str | None) -> str:
    if not isinstance(lang, str) or not lang.strip():
        return _DEFAULT_LANG
    return lang.strip().lower().replace("_", "-").split("-", 1)[0]


def _token_sets_for_lang(lang: str | None) -> tuple[set[str], set[str], set[str]]:
    norm_lang = _normalise_lang(lang)
    data = _LANG_NOISE.get(norm_lang)
    if data is None:
        data = _LANG_NOISE[_DEFAULT_LANG]
    leading = {tok.casefold() for tok in data["leading"]}
    noise = leading | {tok.casefold() for tok in data["noise"]}
    bank = {tok.casefold() for tok in data["bank"]}
    return leading, noise, bank


def _lang_from_meta(meta: dict[str, Any] | None) -> str | None:
    if not isinstance(meta, dict):
        return None
    for key in ("language", "lang"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _trim_party_markers(text: str) -> str:
    """Remove trailing documentary markers (RIF., NUM., CRO …)."""

    if not text:
        return ""
    cleaned = text.strip()
    cleaned = _LEADING_MARKER_PATTERN.sub("", cleaned)
    cleaned = _TRAILING_MARKER_PATTERN.sub("", cleaned)
    return cleaned.strip(" -:;.,")


def _normalize_party_local(name: str) -> str:
    """Local normalisation: strip accents/punctuation, collapse whitespace."""

    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9\s]", " ", s)
    s = re.sub(r"\d+", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    parts = s.split()
    repaired: list[str] = []
    skip_small = {
        "di",
        "de",
        "da",
        "del",
        "della",
        "e",
        "a",
        "al",
        "ai",
        "co",
        "kg",
        "s",
        "r",
        "l",
        "p",
        "sl",
        "sa",
        "slu",
    }
    legal_suffixes = {"srl", "spa", "snc", "sas", "sl", "sa", "slu"}
    for tok in parts:
        if (
            repaired
            and len(tok) <= 2
            and tok not in skip_small
            and repaired[-1] not in legal_suffixes
            and repaired[-1].isalpha()
            and len(repaired[-1]) >= 3
            and tok.isalpha()
        ):
            repaired[-1] = repaired[-1] + tok
        else:
            repaired.append(tok)
    s = " ".join(repaired)
    s = re.sub(r"\bs\s*r\s*l\b", "srl", s)
    s = re.sub(r"\bs\s*p\s*a\b", "spa", s)
    s = re.sub(r"\bs\s*a\s*s\b", "sas", s)
    s = re.sub(r"\bs\s*l\s*u\b", "slu", s)
    s = re.sub(r"\bs\s*l\b", "sl", s)
    s = re.sub(r"\bs\s*a\b", "sa", s)
    return s


def _clean_party_for_evidence(text: str | None, lang: str | None = None) -> str:
    """Canonical normalisation used for evidence tables and beneficiary matching."""

    base = _trim_party_markers((text or "").strip())
    # Drop leading payment verbs (ADDEBITO, BONIFICO, TRANSFERENCIA …)
    base = re.sub(
        r"(?i)^(?:addebito\s+sdd|addebito|accredito|bonifico(?:\s+(?:sepa|istantaneo))?|sdd|rid|pag\.?\s*deb\.?|pagamento|giroconto|transferencia(?:\s+(?:sepa|instant[aá]nea?))?|pago|adeudo(?:\s+(?:directo|domiciliado))?|abono|ingreso|domiciliaci[oó]n)\s*[:#-]*\s*",
        "",
        base,
    )
    # Cut at obvious trailing tokens (commissioni/comisiones, causale/concepto).
    base = re.split(
        r"(?i)\b(?:comm(?:issione)?|causale|comisi[oó]n(?:es)?|concepto)\b",
        base,
        maxsplit=1,
    )[0]
    base = _CURRENCY_PATTERN.sub(" ", base)
    base = re.sub(r"\d+(?:[.,]\d+)?", " ", base)
    norm = _normalize_party_local(base) if base else ""
    if norm:
        tokens = norm.split()
        trimmed = list(tokens)
        filler_tokens = {
            "a",
            "ai",
            "agli",
            "al",
            "alla",
            "alle",
            "allo",
            "di",
            "de",
            "da",
            "del",
            "della",
            "dello",
            "dell",
            "dei",
            "degli",
        }
        leading_lang, noise_lang, bank_lang = _token_sets_for_lang(lang)
        leading_drop = filler_tokens | leading_lang
        while len(trimmed) > 1 and trimmed and trimmed[0] in leading_drop:
            trimmed.pop(0)
        while len(trimmed) > 1 and trimmed and trimmed[-1] in leading_drop:
            trimmed.pop()
        meaningful = [tok for tok in trimmed if tok not in noise_lang]
        if meaningful:
            trimmed = meaningful
        if len(trimmed) > 1:
            trimmed_no_bank = list(trimmed)
            while len(trimmed_no_bank) > 1 and trimmed_no_bank[0] in bank_lang:
                trimmed_no_bank.pop(0)
            while len(trimmed_no_bank) > 1 and trimmed_no_bank[0] in {
                "spa",
                "srl",
                "snc",
                "sas",
                "sl",
                "sa",
                "slu",
            }:
                trimmed_no_bank.pop(0)
            if trimmed_no_bank:
                trimmed = trimmed_no_bank
        norm = " ".join(trimmed)
    if norm:
        tokens = norm.split()
        combined = "".join(tokens)
        if combined and combined not in norm and len(tokens) <= 6:
            norm = f"{norm} {combined}"
    return norm


def _iter_party_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_party_strings(item)
    elif value:
        yield str(value)


def _select_party_candidate(candidates: Iterable[str], lang: str | None = None) -> str:
    best_raw = ""
    best_score = -1
    seen_norm: set[str] = set()
    for raw in candidates:
        clean = raw.strip()
        if not clean:
            continue
        norm = _clean_party_for_evidence(clean, lang)
        if not norm:
            continue
        if norm in seen_norm:
            continue
        seen_norm.add(norm)
        score = len(norm)
        if score > best_score:
            best_score = score
            best_raw = clean
    if best_raw:
        return best_raw
    for raw in candidates:
        clean = raw.strip()
        if clean:
            return clean
    return ""


def _preferred_bank_party(tx: Transaction, meta: dict[str, Any]) -> str:
    """Extract the most informative counterparty string from a bank transaction."""

    desc = tx.description or ""
    candidates: list[str] = []
    fav = re.search(r"(?i)A\s+FAVORE\s+DI\s+([^\n]+)", desc)
    if fav:
        candidates.append((fav.group(1) or "").strip())
    oc = re.search(r"\bo/?c\s*[:#-]?\s*([^,;]+)", desc, flags=re.IGNORECASE)
    if oc:
        candidates.append((oc.group(1) or "").strip())
    for pat in (
        r"ADDEBITO\s+SDD\s+([^\n]+)",
        r"DEB[:\-]?\s*([^\n]+)",
        r"CRED[:\-]?\s*([^\n]+)",
    ):
        m2 = re.search(pat, desc, flags=re.IGNORECASE)
        if m2:
            candidates.append((m2.group(1) or "").strip())
            break
    candidates.extend(_iter_party_strings(meta.get("counter_account_desc")))
    candidates.extend(_iter_party_strings(meta.get("counterpart_name")))
    candidates.extend(_iter_party_strings(meta.get("counterparty")))
    candidates.extend(_iter_party_strings(meta.get("account_desc")))
    if tx.beneficiary:
        candidates.append(tx.beneficiary)
    candidates.append(desc)
    lang = _lang_from_meta(meta)
    return _select_party_candidate(candidates, lang)


def _preferred_ledger_party(tx: Transaction, meta: dict[str, Any]) -> str:
    """Extract the most informative counterparty string from a ledger transaction."""

    candidates: list[str] = []
    for key in (
        "counter_account_desc",
        "extra_desc",
        "details",
        "narrative",
        "causale_desc",
        "movement_desc",
        "memo",
        "account_name",
        "account_desc",
    ):
        candidates.extend(_iter_party_strings(meta.get(key)))
    if tx.beneficiary:
        candidates.append(tx.beneficiary)
    if tx.description:
        candidates.append(tx.description)
    # Avoid returning generic ledger labels when a richer option exists
    ordered = []
    for raw in candidates:
        clean = raw.strip()
        if not clean:
            continue
        ordered.append(clean)
    specific = [c for c in ordered if c.upper() not in _GENERIC_LEDGER_LABELS]
    target_pool = specific or ordered
    lang = _lang_from_meta(meta)
    return _select_party_candidate(target_pool, lang)


def _ledger_payroll_text(
    tx: Transaction,
    meta: dict[str, Any] | None = None,
) -> str:
    """Aggregate ledger fields into an upper-case haystack for payroll tokens."""

    meta = (meta or getattr(tx, "metadata", {}) or {}).copy()
    parts: list[str] = []
    for key in _LEDGER_PAYROLL_KEYS:
        val = meta.get(key)
        if isinstance(val, str):
            trimmed = val.strip()
            if trimmed:
                parts.append(trimmed)
        elif isinstance(val, (list, tuple, set)):
            for item in val:
                if isinstance(item, str):
                    trimmed = item.strip()
                    if trimmed:
                        parts.append(trimmed)
    beneficiary = getattr(tx, "beneficiary", None)
    if beneficiary:
        parts.append(str(beneficiary))
    desc = getattr(tx, "description", None)
    if desc:
        parts.append(str(desc))
    return " ".join(parts).casefold()

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Mapping, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "classify_op",
    "extract_iban",
    "is_tax_ledger_entry",
    "_lex_for",
]


# Lexicon directory
LEXICON_DIR = Path(__file__).resolve().parent.parent / "config" / "lexicon"


def _default_it_lexicon() -> Dict[str, List[str]]:
    return {
        "tax_tokens": ["delega unificata", "erario", "agenzia entrate", " ade "],
        "sdd_tokens": [" sdd ", " rid "],
        "bonifico_tokens": [" bonifico", " sepa", " istantaneo"],
        "fee_tokens": [
            "commissioni",
            "commissione",
            " comm.",
            " canone",
            " imposta di bollo",
            " bollo ",
        ],
        "riba_tokens": [" riba"],
        "card_tokens": [
            "carta",
            " pos ",
            "pagamento carta",
            "card payment",
            "credit card",
            "debit card",
            "visa",
            "mastercard",
        ],
        "withdrawal_terms": [
            "prelievo",
            "prelievi",
            "prelevamento",
            "prelevamenti",
            "withdrawal",
            "contanti",
            "cash",
        ],
        "deposit_terms": ["versamento", "versamenti", "deposito", "depositi"],
        "atm_terms": ["atm", "bancomat", "sportello"],
        "payroll_tokens": [
            "STIPENDIO",
            "STIPENDI",
            "STIPEND",
            "SALARIO",
            "SALARI",
            "SALARI E STIPENDI",
            "SALARIES",
            "SALARY",
            "WAGE",
            "WAGES",
            "PAYROLL",
            "CEDOLINO",
            "BUSTA PAGA",
            "BUSTE PAGA",
            "RETRIBUZIONE",
            "RETRIBUZIONI",
            "PERSONALE",
            "COSTO DEL PERSONALE",
        ],
        "tax_ledger_tokens": [
            "iva",
            "vat",
            "erario",
            "f24",
            "liquidazione iva",
            "debiti tributari",
            "tax",
            "taxes",
            "imposte",
            "imposta",
            "tasse",
            "tributi",
            "inps",
            "inail",
            "irpef",
            "irap",
            "addizionale",
            "ritenute",
            "erario c/",
        ],
    }


def _default_en_lexicon() -> Dict[str, List[str]]:
    return {
        "tax_tokens": [
            "vat",
            "tax",
            "taxes",
            "hmrc",
            "irs",
            "inland revenue",
            "revenue",
        ],
        "sdd_tokens": [
            " direct debit",
            " dd ",
            " ach debit",
            " auto debit",
            " autodirect",
        ],
        "bonifico_tokens": [
            " bank transfer",
            " transfer",
            " wire",
            " sepa",
            " faster payment",
        ],
        "fee_tokens": [
            " fee",
            " fees",
            " commission",
            " service charge",
            " maintenance fee",
            " monthly fee",
            " bank fee",
            " stamp duty",
        ],
        "riba_tokens": [" riba"],
        "card_tokens": [
            " card payment",
            " credit card",
            " debit card",
            " visa ",
            " mastercard",
            " pos ",
        ],
        "withdrawal_terms": [" withdrawal", " cash withdrawal", " cash out", " cash"],
        "deposit_terms": [" deposit", " deposits", " cash deposit"],
        "atm_terms": [" atm", " cashpoint", " cash machine", " branch"],
        "payroll_tokens": [
            "SALARY",
            "SALARIES",
            "PAYROLL",
            "WAGE",
            "WAGES",
            "PAYCHECK",
            "PAY CHEQUE",
            "PAYSLIP",
            "NET PAY",
            "GROSS PAY",
        ],
        "tax_ledger_tokens": [
            "vat",
            "tax",
            "taxes",
            "hmrc",
            "irs",
            "inland revenue",
            "revenue",
            "stamp duty",
        ],
    }


def _default_de_lexicon() -> Dict[str, List[str]]:
    return {
        "tax_tokens": [
            "steuer",
            "mwst",
            "mehrwertsteuer",
            "umsatzsteuer",
            "steueramt",
            "finanzamt",
        ],
        "sdd_tokens": [" lastschrift", " sepa-lastschrift", "einzug"],
        "bonifico_tokens": [" überweisung", " ueberweisung", " sepa", " transfer"],
        "fee_tokens": [
            "gebühr",
            "gebuehr",
            "entgelt",
            "kosten",
            "kontoführung",
            "kartengebühr",
        ],
        "riba_tokens": [" riba"],
        "card_tokens": [
            "karte",
            "kartenzahlung",
            "visa",
            "mastercard",
            " pos ",
            "girocard",
            "ec-karte",
        ],
        "withdrawal_terms": ["abhebung", "barabhebung", "bargeld", "abheben"],
        "deposit_terms": ["einzahlung", "einzahlungen", "bareinzahlung"],
        "atm_terms": ["atm", "geldautomat", "bancomat", "filiale"],
        "payroll_tokens": [
            "gehalt",
            "gehälter",
            "lohn",
            "löhne",
            "salär",
            "lohnabrechnung",
            "payroll",
        ],
        "tax_ledger_tokens": [
            "steuer",
            "mwst",
            "mehrwertsteuer",
            "umsatzsteuer",
            "lohnsteuer",
            "kirchensteuer",
            "finanzamt",
            "steueramt",
        ],
    }


def _default_fr_lexicon() -> Dict[str, List[str]]:
    return {
        "tax_tokens": [
            "tva",
            "impôt",
            "impots",
            "taxe",
            "taxes",
            "trésor public",
            "tresor public",
            "urssaf",
        ],
        "sdd_tokens": [" prélèvement", " prelevement", " sepa"],
        "bonifico_tokens": [" virement", " sepa", " transfert"],
        "fee_tokens": [
            "frais",
            "commission",
            "tenue de compte",
            "frais mensuels",
            "frais bancaires",
        ],
        "riba_tokens": [" riba"],
        "card_tokens": [
            "carte",
            "paiement carte",
            "cb ",
            "visa",
            "mastercard",
            " tpe ",
        ],
        "withdrawal_terms": [
            "retrait",
            "distributeur",
            "guichet",
            "espèces",
            "especes",
        ],
        "deposit_terms": ["dépôt", "depot", "versement", "versements"],
        "atm_terms": ["dab", "distributeur", "guichet", "atm"],
        "payroll_tokens": [
            "salaire",
            "salaires",
            "paie",
            "payroll",
            "bulletin de paie",
            "fiche de paie",
            "paye",
        ],
        "tax_ledger_tokens": [
            "tva",
            "impôt",
            "impots",
            "taxe",
            "taxes",
            "urssaf",
            "trésor public",
            "tresor public",
        ],
    }


def _default_es_lexicon() -> Dict[str, List[str]]:
    return {
        "tax_tokens": [
            "iva",
            "impuesto",
            "impuestos",
            "agencia tributaria",
            "aeat",
            "hacienda",
        ],
        "sdd_tokens": [
            "adeudo directo",
            "adeudo domiciliado",
            "domiciliacion",
            "recibo domiciliado",
        ],
        "bonifico_tokens": [
            "transferencia",
            "giro bancario",
            "sepa",
            "bizum",
        ],
        "fee_tokens": [
            "comision",
            "comisiones",
            "gastos bancarios",
            "mantenimiento de cuenta",
            "cuota de mantenimiento",
        ],
        "riba_tokens": ["recibo bancario", "remesa"],
        "card_tokens": [
            "tarjeta",
            "pago con tarjeta",
            "visa",
            "mastercard",
            "tpv",
        ],
        "withdrawal_terms": [
            "retirada",
            "reintegro",
            "extraccion",
            "sacar efectivo",
            "efectivo",
        ],
        "deposit_terms": ["ingreso", "deposito", "consignacion"],
        "atm_terms": ["atm", "cajero", "cajero automatico", "sucursal"],
        "payroll_tokens": [
            "SALARIO",
            "SALARIOS",
            "SUELDO",
            "SUELDOS",
            "NOMINA",
            "NOMINAS",
        ],
        "tax_ledger_tokens": [
            "iva",
            "impuesto",
            "impuestos",
            "agencia tributaria",
            "aeat",
            "hacienda",
            "retencion",
            "retenciones",
        ],
    }


def _load_lang_lexicon(lang: str) -> Dict[str, List[str]]:
    lang = (lang or "").strip().lower()
    if lang.startswith("en"):
        cfg = LEXICON_DIR / "en.json"
        base = _default_en_lexicon()
    elif lang.startswith("de"):
        cfg = LEXICON_DIR / "de.json"
        base = _default_de_lexicon()
    elif lang.startswith("fr"):
        cfg = LEXICON_DIR / "fr.json"
        base = _default_fr_lexicon()
    elif lang.startswith("es"):
        cfg = LEXICON_DIR / "es.json"
        base = _default_es_lexicon()
    else:
        cfg = LEXICON_DIR / "it.json"
        base = _default_it_lexicon()
    try:
        if cfg.exists():
            data = json.loads(cfg.read_text(encoding="utf-8"))
            for k, v in data.items():
                if isinstance(v, list):
                    base[k] = [str(x) for x in v]
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to load %s lexicon file %s: %s", lang or "it", cfg, exc)
    return base


_IT_LEXICON = _load_lang_lexicon("it")


def _lex_for(lang: Optional[str]) -> Dict[str, List[str]]:
    if not lang:
        return _IT_LEXICON
    l = str(lang).strip().lower()
    if l.startswith("en"):
        global _EN_LEXICON
        try:
            _EN_LEXICON
        except NameError:
            _EN_LEXICON = _load_lang_lexicon("en")
        return _EN_LEXICON
    if l.startswith("de"):
        global _DE_LEXICON
        try:
            _DE_LEXICON
        except NameError:
            _DE_LEXICON = _load_lang_lexicon("de")
        return _DE_LEXICON
    if l.startswith("fr"):
        global _FR_LEXICON
        try:
            _FR_LEXICON
        except NameError:
            _FR_LEXICON = _load_lang_lexicon("fr")
        return _FR_LEXICON
    if l.startswith("es"):
        global _ES_LEXICON
        try:
            _ES_LEXICON
        except NameError:
            _ES_LEXICON = _load_lang_lexicon("es")
        return _ES_LEXICON
    return _IT_LEXICON


def extract_iban(text: str) -> Optional[str]:
    if not text:
        return None
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    m = re.search(r"\b([A-Z]{2}\d{2}[A-Z0-9]{11,30})\b", s, flags=re.IGNORECASE)
    if not m:
        return None
    return re.sub(r"\s+", "", m.group(1).upper())


def classify_op(description: str, lang: Optional[str] = None) -> str:
    s = (
        unicodedata.normalize("NFKD", description or "")
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    s = " ".join(s.split())
    if not s:
        return "OTHER"
    lex = _lex_for(lang)
    if "f24" in s or any(tok in s for tok in lex.get("tax_tokens", [])):
        return "F24"
    if any(tok in s for tok in lex.get("sdd_tokens", [])):
        return "SDD"
    if any(tok in s for tok in lex.get("bonifico_tokens", [])):
        return "BONIFICO"
    if (
        any(tok in s for tok in lex.get("withdrawal_terms", []))
        or any(tok in s for tok in lex.get("deposit_terms", []))
    ) and any(tok in s for tok in lex.get("atm_terms", [])):
        return "ATM"
    if any(tok in s for tok in lex.get("card_tokens", [])):
        return "CARD"
    if any(tok in s for tok in lex.get("fee_tokens", [])):
        return "FEE"
    if any(tok in s for tok in lex.get("riba_tokens", [])):
        return "RIBA"
    return "OTHER"


def is_tax_ledger_entry(tx: Mapping[str, object] | object) -> bool:
    try:
        meta = getattr(tx, "metadata", None)
    except Exception:
        meta = None
    if not isinstance(meta, Mapping):
        meta = {}
    if meta.get("tax_flag") is True:
        return True
    fields: List[str] = []
    for k in (
        "counter_account",
        "counter_account_desc",
        "account_desc",
        "account_name",
        "counterparty_account",
    ):
        v = meta.get(k)
        if isinstance(v, str):
            fields.append(v)
    try:
        desc = getattr(tx, "description", "")
    except Exception:
        desc = ""
    fields.append(desc or "")
    blob = (
        unicodedata.normalize("NFKD", " ".join(fields))
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    try:
        lang_hint = None
        if isinstance(meta, Mapping):
            lang_hint = meta.get("language") or meta.get("lang")
    except Exception:
        lang_hint = None
    lex = _lex_for(lang_hint)
    tax_tokens = lex.get("tax_ledger_tokens", [])
    return any(tok in blob for tok in tax_tokens)

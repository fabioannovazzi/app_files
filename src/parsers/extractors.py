"""Utilities for extracting references and beneficiary names from transaction descriptions.

Patterns cover common formats across Italian, English, German, French, and Spanish statements. They
are not exhaustive and can be extended as new cases arise. Matching is case- and accent-insensitive.
"""

from __future__ import annotations

import re
import string
import unicodedata
from typing import List, Optional


def _strip_accents(text: str) -> str:
    """Return ``text`` without diacritical marks."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


"""Reference identifier regexes across languages and formats.

We accept identifiers containing digits/letters and common separators ("-", "/", ".").
This captures variants such as:
 - "Num. Bonifico 240938080014162-484842052630"
 - "Num.Bon.Sepa 240931000123672"
 - "RIF. 24093/0008035071"
 - CRO/TRN alphanumerics
 - Invoice numbers (fattura/invoice/facture/rechnung)
"""
REFERENCE_PATTERNS = [
    # Bonifico/Bon.Sepa numbers (allow hyphens/slashes and letters when present)
    r"\b(?:num(?:ero)?\.?|n\.?)\s*bon(?:\.|ifico)?(?:\.?\s*sepa)?[^A-Za-z0-9]*[:#]?\s*([A-Z0-9][A-Z0-9\-\/.]*)",
    # RIF. (Italian reference shorthand)
    r"\brif\.?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-\/.]*)",
    # Wire transfer IDs (CRO, CRO UIC, CRO code)
    r"\b(?:bonifico\s*)?cro(?:\s*uic)?(?:\s*code)?\s*[:#]?\s*([A-Z0-9\-\/.]+)",
    r"\bnumero\s*cro\s*[:#]?\s*([A-Z0-9\-\/.]+)",
    # SEPA transfer numbers (TRN)
    r"\b(?:num(?:ero)?\s*)?trn\s*([A-Z0-9\-\/.]+)",
    # Mandate IDs
    r"\bmandate\s*id\s*[:#]?\s*([A-Z0-9\-\/.]+)",
    # Invoice identifiers across languages
    r"\bfattur[ai]\s*n(?:o)?\.?\s*([A-Z0-9\-\/.]+)",
    # Common short form without "n"/"no": "fattura 123", "fatture 2024/001"
    r"\bfattur[ai]\s*([0-9][A-Z0-9\-\/.]*)",
    r"\b(?:invoice|inv)\s*(?:#|n(?:o)?\.?)?\s*([A-Z0-9\-\/.]+)",
    r"\bref(?:erence)?\s*[:#]?\s*([A-Z0-9\-\/.]+)",
    r"\brech\.?[- ]?nr\.?\s*([A-Z0-9\-\/.]+)",
    r"\brechnungs?(?:nummer|nr\.?|num\.?)\s*[:#]?\s*([A-Z0-9\-\/.]+)",
    r"\bfacture\s+n(?:o)?\.?\s*([A-Z0-9\-\/.]+)",
    r"\bfactura\s+n(?:o)?\.?\s*([A-Z0-9\-\/.]+)",
    # Protocol numbers (e.g., "RIF.PROT.N. 30330981", "PROT.N. 30330981")
    r"\bprot\.?[- ]?n\.?\s*([A-Z0-9\-\/.]+)",
    r"\bprotocol(?:lo)?\s*[:#]?\s*([A-Z0-9\-\/.]+)",
    # Cheque numbers
    r"\bassegno\s+n(?:o)?\.?\s*([A-Z0-9\-\/.]+)",
    r"\b(?:cheque|check)\s*(?:n(?:o)?\.?|number|#)\s*([A-Z0-9\-\/.]+)",
    r"\bscheck\s*(?:nr\.?|nummer|#)\s*([A-Z0-9\-\/.]+)",
    # Generic shorthand 'N.' often used before document numbers.
    # Accept 1–8 alphanumeric segments but require at least one separator so we
    # don't capture stray numbers like day-of-month (e.g. "15").
    r"\bn\.?\s*([A-Z0-9]{1,12}(?:[/_-][A-Z0-9]{1,12}){1,3})",
]

# Phrases indicating the beneficiary/payee across multiple languages.
BENEFICIARY_PATTERNS = [
    # Italian
    r"a\s+favore\s+di\s+([^,;]+)",
    r"a\s*fav\.?\s*di\s+([^,;]+)",
    r"per\s+beneficiario\s+([^,;]+)",
    r"versamento\s+a\s+favore\s+di\s+([^,;]+)",
    r"fattura\s+(?:di\s+)?([A-Za-z][^,;]+)",
    # English
    r"to\s+(?:beneficiary\s+)?(?:the\s+)?([^\d,;]+)",
    r"payee\s*[:#]?\s*([^,;]+)",
    r"received\s+from\s+([^,;]+)",
    r"paid\s+to\s+([^,;]+)",
    # German
    r"(?:zu|an)\s+gunsten\s+([^\d,;]+)",
    r"zugunsten\s+([^\d,;]+)",
    r"empfanger\s*[:#]?\s*([^,;]+)",
    r"zahlung\s+an\s+([^,;]+)",
    r"von(?:\s+dem\s+konto)?\s+([^,;]+)",
    # French
    r"au\s+profit\s+de\s+([^\d,;]+)",
    r"au\s+nom\s+de\s+([^,;]+)",
    r"au\s+beneficiaire\s+de\s+([^,;]+)",
    r"virement\s+a\s+([^,;]+)",
    r"recu\s+de\s+([^,;]+)",
    # Spanish
    r"a\s+nombre\s+de\s+([^\d,;]+)",
    r"pagado\s+a\s+([^,;]+)",
    r"pagado\s+por\s+([^,;]+)",
    r"remitente\s*[:#]?\s*([^,;]+)",
    r"destinatario\s*[:#]?\s*([^,;]+)",
    # Generic "o/c:" (common on Italian statements for the counterparty)
    r"\bo/?c\s*[:#-]?\s*([^,;]+)",
    r"bonifico\s+o/?c\s*[:#-]?\s*([^,;]+)",
    # Sender/Originator synonyms across languages
    r"ordinante\s*[:#]?\s*([^,;]+)",
    r"mittente\s*[:#]?\s*([^,;]+)",
    r"auftraggeber\s*[:#]?\s*([^,;]+)",
    r"emetteur\s*[:#]?\s*([^,;]+)",
    r"ordenante\s*[:#]?\s*([^,;]+)",
    # Salary/payroll phrasing (beneficiary implied by name after keyword)
    # English
    r"\bsalary\s+(?:for\s+)?([^\d,;]+)",
    r"\bwages?\s+(?:for\s+)?([^\d,;]+)",
    r"\bpayroll\s+(?:for\s+)?([^\d,;]+)",
    # Italian
    r"\bstipendi(?:o|i)\s+(?:per\s+)?([^\d,;]+)",
    r"\bsalario\s+(?:per\s+)?([^\d,;]+)",
    r"\bbusta\s+paga\s+(?:di\s+|per\s+)?([^\d,;]+)",
    r"\bretribuzion(?:e|i)\s+(?:di\s+|per\s+)?([^\d,;]+)",
    r"\bcedolino\s+(?:di\s+|per\s+)?([^\d,;]+)",
    # Spanish
    r"\bnomina\s+(?:de\s+|para\s+)?([^\d,;]+)",
    r"\bsueldo\s+(?:para\s+)?([^\d,;]+)",
    # German
    r"\bgehalt\s+(?:f[uü]r\s+)?([^\d,;]+)",
    # French
    r"\bsalaire\s+(?:pour\s+)?([^\d,;]+)",
]


def normalise_name(name: str) -> str:
    """Return a normalised version of ``name`` for comparisons.

    - Strip accents and punctuation
    - Collapse whitespace
    - Normalise common Italian legal suffixes (SRL, SPA, SAS)
    """
    name_norm = _strip_accents(name)
    name_norm = "".join(ch for ch in name_norm if ch not in string.punctuation)
    name_norm = re.sub(r"\s+", " ", name_norm).strip().lower()
    # Repair odd splits like "stabi le" -> "stabile" while avoiding joining common
    # short function words or legal suffixes (di,de,da,e,a,spa,srl,snc,sas,co,kg).
    tokens = name_norm.split()
    repaired: list[str] = []
    skip_small = {"di", "de", "da", "del", "della", "e", "a", "al", "ai", "co", "kg"}
    legal_suffixes = {"srl", "spa", "snc", "sas"}
    for t in tokens:
        if (
            repaired
            and len(t) <= 2
            and t not in skip_small
            and repaired[-1] not in legal_suffixes
            and repaired[-1].isalpha()
            and len(repaired[-1]) >= 3
            and t.isalpha()
        ):
            repaired[-1] = repaired[-1] + t
        else:
            repaired.append(t)
    name_norm = " ".join(repaired)
    # Collapse spaced variants of legal suffixes (e.g. "s r l" → "srl")
    name_norm = re.sub(r"\bs\s*r\s*l\b", "srl", name_norm)
    name_norm = re.sub(r"\bs\s*p\s*a\b", "spa", name_norm)
    name_norm = re.sub(r"\bs\s*a\s*s\b", "sas", name_norm)
    return name_norm


def extract_references(text: str) -> List[str]:
    """Extract reference identifiers from ``text``.

    Returns a de‑duplicated list preserving first occurrence order. Adds a few
    normalised variants to improve cross‑source equality checks:
    - Unify separators (``-``/``_`` → ``/``)
    - Expand Italian FE invoice tokens (e.g. ``FE_3079_23`` → ``3079/23`` and ``3079/2023``)
    - Keep composite transfer ids intact and, when an IBAN is present on the right
      side of a hyphen, also keep the left segment separately.
    """
    text_norm = _strip_accents(text)
    raw: List[str] = []
    for pattern in REFERENCE_PATTERNS:
        for match in re.finditer(pattern, text_norm, flags=re.IGNORECASE):
            raw.append(match.group(1).strip())

    def _add_variant(acc: List[str], token: str) -> None:
        t = token.strip().strip("./-_")
        if not t:
            return
        if t not in acc:
            acc.append(t)
        # Separator‑normalised variant (helps dash/underscore/slash mismatches)
        norm_sep = re.sub(r"[-_]", "/", t)
        if norm_sep not in acc:
            acc.append(norm_sep)
        # FE invoice shorthand: FE_<num>_<yy|yyyy>
        m = re.match(r"(?i)fe[/_-]?(\d{2,6})[/_-]?(\d{2,4})$", t)
        if m:
            num, yy = m.group(1), m.group(2)
            # keep num/yy
            short = f"{num}/{yy}"
            if short not in acc:
                acc.append(short)
            if len(yy) == 2:
                yyyy = ("20" + yy) if int(yy) < 70 else ("19" + yy)
            else:
                yyyy = yy
            long = f"{num}/{yyyy}"
            if long not in acc:
                acc.append(long)

    extended: List[str] = []
    for r in raw:
        _add_variant(extended, r)
        # Composite forms like "<ref>-<iban>" → also keep left segment when right looks like IBAN
        if "-" in r:
            left, right = r.split("-", 1)
            if re.search(r"\bIT[0-9A-Z]{13,30}\b", right, flags=re.IGNORECASE):
                _add_variant(extended, left)
    # Deduplicate preserving order
    return list(dict.fromkeys(extended))


def extract_beneficiary(text: str) -> Optional[str]:
    """Extract and normalise a beneficiary name from ``text`` if present."""
    text_norm = _strip_accents(text)
    # 1) Patterned matches first (o/c, a favore di, invoice "di", etc.)
    for pattern in BENEFICIARY_PATTERNS:
        match = re.search(pattern, text_norm, flags=re.IGNORECASE)
        if match:
            cand = match.group(1).strip()
            # Trim trailing markers and obvious reference segments accidentally captured
            cand = re.split(
                r"(?i)\b(?:num(?:ero)?\.?\s*bon(?:\.|ifico)?|bon\.?\s*sepa|rif\.|cro|trn|iban|abi-?cab|prot\.?\s*n\.|fattur[ai]|invoice|ref\b)\b",
                cand,
                maxsplit=1,
            )[0].strip(" -:;.,")
            return normalise_name(cand)
    # 2) Ledger‑style: capture trailing entity after an "N.<doc> [del <date>]" token
    m = re.search(
        r"\bn\.?\s*[A-Z0-9/_-]+(?:\s+del\s+\d{1,2}[./-]?\d{1,2}[./-]?\d{2,4})?\s+([A-Za-z][^,;]+)$",
        text_norm,
        flags=re.IGNORECASE,
    )
    if m:
        return normalise_name(m.group(1).strip())
    return None

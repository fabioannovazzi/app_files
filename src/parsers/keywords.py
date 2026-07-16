"""Keyword lists for bank statement parsing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class KeywordMap:
    incoming: List[str]
    outgoing: List[str]
    currencies: List[str]


KEYWORDS = KeywordMap(
    incoming=[
        "bonifico o/c",
        "accredito",
        "ri-entr",
        "gutschrift",
        "eingang",
        "virement reçu",
        "crédit",
        "credit transfer",
        "deposit",
    ],
    outgoing=[
        "disposizione a favore",
        "addebito sdd",
        "sdd",
        "lastschrift",
        "prélèvement",
        "pagamento carta",
        "card payment",
        "credit card",
        "debit card",
        "visa",
        "mastercard",
        "assegno",
        "cheque",
        "pagamento f24",
        "commissioni",
        "fees",
        "canone",
    ],
    currencies=["EUR", "€", "CHF", "Fr.", "USD", "$", "GBP", "£"],
)

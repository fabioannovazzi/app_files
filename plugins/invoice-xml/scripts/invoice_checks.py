"""Local arithmetic and field consistency checks, distinct from SdI acceptance."""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from typing import Any

__all__ = ["check_invoice"]

CENT = Decimal("0.01")
ZERO = Decimal("0")


def _rows(value: Any) -> list[dict[str, Any]]:
    return value if isinstance(value, list) else [value]


def _amount(row: dict[str, Any], field: str, default: str | None = None) -> Decimal:
    value = row.get(field, default)
    if not isinstance(value, str):
        raise ValueError(f"Missing decimal {field}")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal {field}") from exc
    if not amount.is_finite():
        raise ValueError(f"Nonfinite decimal {field}")
    return amount


def _key(row: dict[str, Any]) -> tuple[Decimal, str]:
    return _amount(row, "AliquotaIVA"), row.get("Natura", "")


def _vat_consistency(
    row: dict[str, Any], label: str, issues: list[str], invoice_date: str
) -> None:
    rate, nature = _key(row)
    if (rate == ZERO) != bool(nature):
        issues.append(
            f"{label}: Natura is required at zero VAT and excluded at nonzero VAT"
        )
    if nature.startswith("N6") and row.get("EsigibilitaIVA") == "S":
        issues.append(f"{label}: reverse charge and split payment conflict")
    if invoice_date >= "2021-01-01" and nature in {"N2", "N3", "N6"}:
        issues.append(
            f"{label}: generic Natura {nature} is retired from 2021; review the specific code"
        )


def check_invoice(invoice: dict[str, Any], route: str) -> list[str]:
    """Check schema-valid fields without choosing tax codes or changing amounts.

    Decimal arithmetic is required for reproducible money. The cent tolerance is
    this workflow's reconciliation policy, not a claim to reproduce all SdI rules.
    Complex header adjustments are withheld until separately qualified; no fields
    are silently removed in order to make a document exportable.
    """
    issues: list[str] = []
    header = invoice["FatturaElettronicaHeader"]
    transmission = header["DatiTrasmissione"]
    if transmission["FormatoTrasmissione"] != "FPR12":
        issues.append("Only ordinary private-recipient FPR12 export is qualified")
    if len(transmission["CodiceDestinatario"]) != 7:
        issues.append("FPR12 requires a seven-character recipient code")
    if (
        transmission.get("PECDestinatario")
        and transmission["CodiceDestinatario"] != "0000000"
    ):
        issues.append("PEC routing requires recipient code 0000000")
    if route not in {"domestic", "foreign_integration"}:
        issues.append("Select and review domestic or foreign_integration preparation")
    bodies = _rows(invoice["FatturaElettronicaBody"])
    identities: set[tuple[str, str, str]] = set()
    with localcontext() as context:
        context.prec = 50
        for index, body in enumerate(bodies):
            label = f"Invoice body {index + 1}"
            general = body["DatiGenerali"]["DatiGeneraliDocumento"]
            document_type = general["TipoDocumento"]
            allowed = (
                {"TD17", "TD18", "TD19"}
                if route == "foreign_integration"
                else {
                    "TD01",
                    "TD02",
                    "TD03",
                    "TD04",
                    "TD05",
                    "TD06",
                    "TD24",
                    "TD25",
                    "TD26",
                }
            )
            if document_type not in allowed:
                issues.append(f"{label}: document type is outside the selected route")
            identity = (document_type, general["Data"], general["Numero"])
            if identity in identities:
                issues.append(f"{label}: duplicate invoice identity within the export")
            identities.add(identity)
            if route == "foreign_integration":
                if (
                    header["CedentePrestatore"]["DatiAnagrafici"]["IdFiscaleIVA"][
                        "IdPaese"
                    ]
                    == "IT"
                ):
                    issues.append(
                        f"{label}: foreign integration needs the supplier's foreign identifier"
                    )
                customer = header["CessionarioCommittente"]["DatiAnagrafici"]
                if customer.get("IdFiscaleIVA", {}).get("IdPaese") != "IT":
                    issues.append(
                        f"{label}: foreign integration requires the Italian customer's VAT identity"
                    )
                links = body["DatiGenerali"].get("DatiFattureCollegate", [])
                if not links or any(not row.get("Data") for row in _rows(links)):
                    issues.append(
                        f"{label}: record original invoice number and date separately"
                    )
            if general["Divisa"] != "EUR":
                issues.append(
                    f"{label}: this export profile requires reviewed EUR amounts and conversion evidence"
                )
            for special in ("DatiBollo", "ScontoMaggiorazione", "Art73"):
                if special in general:
                    issues.append(
                        f"{label}: {special} total reconciliation is not yet qualified; retained for review"
                    )
            lines = _rows(body["DatiBeniServizi"]["DettaglioLinee"])
            summaries = _rows(body["DatiBeniServizi"]["DatiRiepilogo"])
            line_numbers: set[int] = set()
            bases: dict[tuple[Decimal, str], Decimal] = defaultdict(lambda: ZERO)
            for line in lines:
                number = int(line["NumeroLinea"])
                if number in line_numbers:
                    issues.append(f"{label}: duplicate line number {number}")
                line_numbers.add(number)
                _vat_consistency(
                    line, f"{label}, line {number}", issues, general["Data"]
                )
                unit = _amount(line, "PrezzoUnitario")
                for adjustment in _rows(line.get("ScontoMaggiorazione", [])):
                    if "Importo" not in adjustment and "Percentuale" not in adjustment:
                        issues.append(
                            f"{label}, line {number}: discount/surcharge has no value"
                        )
                        continue
                    adjustment_amount = (
                        _amount(adjustment, "Importo")
                        if "Importo" in adjustment
                        else unit * _amount(adjustment, "Percentuale") / 100
                    )
                    unit += (
                        adjustment_amount
                        if adjustment["Tipo"] == "MG"
                        else -adjustment_amount
                    )
                expected = unit * _amount(line, "Quantita", "1")
                if abs(expected - _amount(line, "PrezzoTotale")) > CENT:
                    issues.append(
                        f"{label}, line {number}: quantity × adjusted unit price does not reconcile to line total"
                    )
                bases[_key(line)] += _amount(line, "PrezzoTotale")
                if line.get("Ritenuta") == "SI" and not general.get("DatiRitenuta"):
                    issues.append(
                        f"{label}, line {number}: withholding flagged without DatiRitenuta"
                    )
            for contribution in _rows(general.get("DatiCassaPrevidenziale", [])):
                _vat_consistency(
                    contribution,
                    f"{label}, pension contribution",
                    issues,
                    general["Data"],
                )
                bases[_key(contribution)] += _amount(
                    contribution, "ImportoContributoCassa"
                )
            summarized: dict[tuple[Decimal, str], Decimal] = defaultdict(lambda: ZERO)
            gross = ZERO
            for summary in summaries:
                _vat_consistency(
                    summary, f"{label}, VAT summary", issues, general["Data"]
                )
                taxable = _amount(summary, "ImponibileImporto")
                tax = _amount(summary, "Imposta")
                expected_tax = (
                    taxable * _amount(summary, "AliquotaIVA") / 100
                ).quantize(CENT, rounding=ROUND_HALF_UP)
                if abs(expected_tax - tax) > CENT:
                    issues.append(
                        f"{label}: VAT amount does not reconcile to taxable base × rate"
                    )
                summarized[_key(summary)] += taxable - _amount(
                    summary, "Arrotondamento", "0"
                )
                gross += taxable + tax
            if set(bases) != set(summarized):
                issues.append(
                    f"{label}: line/contribution VAT groups differ from summary groups"
                )
            for group in set(bases) | set(summarized):
                if abs(bases[group] - summarized[group]) > CENT:
                    issues.append(
                        f"{label}: taxable summary does not reconcile to lines and contributions for VAT group {group}"
                    )
            if "ImportoTotaleDocumento" not in general:
                issues.append(f"{label}: review and supply the document total")
            elif (
                abs(
                    gross
                    + _amount(general, "Arrotondamento", "0")
                    - _amount(general, "ImportoTotaleDocumento")
                )
                > CENT
            ):
                issues.append(
                    f"{label}: document total does not reconcile to taxable bases, VAT and rounding"
                )
    return issues

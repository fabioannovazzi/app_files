"""Evidence-bound legal citation records; source selection and judgments stay model-led."""

from __future__ import annotations

import argparse
import html
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker
from legal_documents import read_pack

__all__ = ["scaffold", "validate_citations", "render_citations", "main"]

LOGGER = logging.getLogger(__name__)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def scaffold(
    run_dir: Path, document_ids: list[str], scope: str, language: str = "it"
) -> Path:
    """Identify documents to inspect; imported authorities are registered separately."""
    pack = read_pack(run_dir)
    available = {s["id"] for s in pack["sources"]}
    if (
        not document_ids
        or len(set(document_ids)) != len(document_ids)
        or set(document_ids) - available
    ):
        raise ValueError("Select distinct document IDs from the evidence pack.")
    if not scope.strip() or language not in {"it", "en", "fr", "de", "es"}:
        raise ValueError("State the verification scope and supported language.")
    value = {
        "schema_version": 1,
        "language": language,
        "scope": scope,
        "inventory": {
            source_id: {
                "reviewed_anchors": [],
                "limitations": ["Document citation inventory not yet reviewed."],
            }
            for source_id in document_ids
        },
        "authorities": [],
        "claims": [],
        "limitations": [],
    }
    target = run_dir / "citations.json"
    with target.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return target


def validate_citations(run_dir: Path, value: dict[str, Any]) -> dict[str, Any]:
    """Check quotes, declared coverage and consistency, never legal truth."""
    pack = read_pack(run_dir)
    sources = {s["id"]: s for s in pack["sources"]}
    schema = _load(Path(__file__).with_suffix(".schema.json"))
    errors = [
        f"{e.json_path}: {e.message}"
        for e in Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(value)
    ]
    if errors:
        return {
            "valid": False,
            "inventory_complete": False,
            "checks": [],
            "errors": errors,
            "limitations": [],
        }
    units = {
        (s["id"], u["anchor"]): u["text"] for s in sources.values() for u in s["units"]
    }
    limits = list(value["limitations"])

    def quote_matches(citation: dict[str, str], owner: str) -> None:
        text = units.get((citation["source_id"], citation["anchor"]), "")
        quote = " ".join(citation["quote"].split())
        if not quote or quote not in " ".join(text.split()):
            errors.append(f"{owner}: quotation not found at the cited anchor.")

    def covered(source_id: str | None, anchors: list[str], owner: str) -> bool:
        if source_id not in sources:
            errors.append(f"{owner}: unknown source ID.")
            return False
        source = sources[source_id]
        expected = {u["anchor"] for u in source["units"]}
        if set(anchors) - expected:
            errors.append(f"{owner}: unknown reviewed anchor.")
        return bool(expected) and set(anchors) == expected and not source["error"]

    inventory_complete = True
    for source_id, record in value["inventory"].items():
        full = covered(source_id, record["reviewed_anchors"], source_id)
        if not full or record["limitations"]:
            inventory_complete = False
            limits.append(source_id + ": citation inventory incomplete.")
        limits.extend(source_id + ": " + item for item in record["limitations"])
    authorities = {a["id"]: a for a in value["authorities"]}
    if len(authorities) != len(value["authorities"]):
        errors.append("Authority IDs must be unique.")
    fully_read = {}
    for authority in value["authorities"]:
        aid = authority["id"]
        if authority["url"]:
            url = urlsplit(authority["url"])
            if (
                url.scheme not in {"https", "http"}
                or not url.hostname
                or url.username
                or url.password
            ):
                errors.append(
                    f"{aid}: use a public HTTP(S) source URL without credentials."
                )
        if authority["access"] == "unavailable":
            if authority["source_id"] is not None or authority["reviewed_anchors"]:
                errors.append(
                    f"{aid}: an unavailable authority cannot claim inspected source material."
                )
            if not authority["limitations"]:
                errors.append(f"{aid}: explain the source access limitation.")
            fully_read[aid] = False
        else:
            fully_read[aid] = covered(
                authority["source_id"], authority["reviewed_anchors"], aid
            )
            if authority["source_id"] in value["inventory"]:
                errors.append(
                    f"{aid}: the document under review cannot verify its own citation."
                )
        limits.extend(aid + ": " + item for item in authority["limitations"])
    ids = [c["id"] for c in value["claims"]]
    if len(ids) != len(set(ids)):
        errors.append("Claim IDs must be unique.")
    checks = []
    for claim in value["claims"]:
        cid = claim["id"]
        passage = claim["document_passage"]
        if passage["source_id"] not in value["inventory"]:
            errors.append(f"{cid}: claim is outside the selected document inventory.")
        quote_matches(passage, cid)
        authority_ids = [c["authority_id"] for c in claim["checks"]]
        if len(set(authority_ids)) != len(authority_ids):
            errors.append(f"{cid}: duplicate authority check.")
        for check in claim["checks"]:
            aid = check["authority_id"]
            authority = authorities.get(aid)
            if authority is None:
                errors.append(f"{cid}: unknown authority {aid}.")
                continue
            for citation in check["passages"]:
                if citation["source_id"] != authority["source_id"]:
                    errors.append(
                        f"{cid}/{aid}: cited passage belongs to another authority."
                    )
                quote_matches(citation, cid + "/" + aid)
            if authority["access"] == "unavailable" and (
                check["passages"]
                or check["identity"] != "unresolved"
                or check["version"] != "unresolved"
                or check["support"] != "unresolved"
            ):
                errors.append(
                    f"{cid}/{aid}: inaccessible source cannot carry a verified judgment."
                )
            if (
                any(
                    check[key] != "unresolved"
                    for key in ("identity", "version", "support")
                )
                and not check["passages"]
            ):
                errors.append(
                    f"{cid}/{aid}: substantive source judgment needs inspected passages."
                )
            complete_source = (
                authority["access"] == "full-text"
                and fully_read[aid]
                and not authority["limitations"]
            )
            if check["identity"] == "mismatch":
                result = "wrong-identity"
            elif check["version"] == "wrong-version":
                result = "wrong-version"
            elif (
                check["identity"] != "matched"
                or check["version"] != "applicable"
                or not complete_source
            ):
                result = "unverified"
            else:
                result = {
                    "supports": "supported",
                    "partial": "partial",
                    "contradicts": "not-supported",
                    "does-not-address": "not-supported",
                    "unresolved": "unverified",
                }[check["support"]]
            checks.append({"claim_id": cid, "authority_id": aid, "result": result})
    return {
        "valid": not errors,
        "inventory_complete": inventory_complete and not errors,
        "checks": checks,
        "errors": errors,
        "limitations": limits,
        "meaning": "Recorded model judgments with mechanically checked source links and quotations; not certification of legal truth, source authenticity or completeness of research.",
    }


def render_citations(run_dir: Path, review_path: Path) -> Path:
    """Publish the source-to-claim record, with unresolved access and versions visible."""
    value = _load(review_path)
    result = validate_citations(run_dir, value)
    target = run_dir / "citations.html"
    if target.exists():
        number = 1
        while (run_dir / f"previous-{number}-citations.html").exists():
            number += 1
        target.rename(run_dir / f"previous-{number}-citations.html")
    (run_dir / "citations-validation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not result["valid"]:
        raise ValueError("Invalid citation review: " + "; ".join(result["errors"]))
    labels = _load(Path(__file__).with_name("legal_citations_labels.json"))[
        value["language"]
    ]
    esc = lambda text: html.escape(str(text), quote=True)
    authorities = {a["id"]: a for a in value["authorities"]}
    statuses = {
        (c["claim_id"], c["authority_id"]): c["result"] for c in result["checks"]
    }
    rows = []
    evidence_html = (
        lambda c: f"<p>{esc(c['source_id'])} · {esc(c['anchor'])}</p><blockquote>{esc(c['quote'])}</blockquote>"
    )
    for claim in value["claims"]:
        for check in claim["checks"]:
            aid = check["authority_id"]
            source = authorities[aid]
            status = labels["results"][statuses[(claim["id"], aid)]]
            judgments = " · ".join(
                labels["judgments"][check[k]]
                for k in ("identity", "version", "support")
            )
            rows.append(
                f"<tr><th>{esc(claim['id'])}<p>{esc(claim['proposition'])}</p>{evidence_html(claim['document_passage'])}</th><td>{esc(source['citation'])}<p>{esc(labels['relevant_date'])}: {esc(claim['relevant_date'])}</p><p>{esc(judgments)}</p>{''.join(evidence_html(c) for c in check['passages'])}</td><td><strong>{esc(status)}</strong><p>{esc(check['reasoning'])}</p><p>{esc(claim['correction'])}</p></td></tr>"
            )
    register = []
    for source in value["authorities"]:
        link = (
            f'<a href="{esc(source["url"])}" rel="noreferrer">{esc(source["citation"])}</a>'
            if source["url"]
            else esc(source["citation"])
        )
        register.append(
            f"<li><strong>{esc(source['id'])}</strong> {link}<p>{esc(labels['access'][source['access']])} · {esc(labels['checked'])}: {esc(source['checked_at'])}</p><p>{esc(labels['version'])}: {esc(source['version'])}</p><p>{esc('; '.join(source['limitations']))}</p></li>"
        )
    page = f"""<!doctype html><html lang="{value['language']}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(labels['title'])}</title>
<style>body{{font:16px/1.6 'Instrument Sans',sans-serif;color:#172b4d;max-width:1200px;margin:40px auto;padding:0 24px}}h1,h2{{line-height:1.2}}h2{{margin-top:36px}}table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{border:1px solid #ccd5df;padding:14px;text-align:left;vertical-align:top;font-weight:400}}thead th{{font-weight:700}}blockquote{{margin:8px 0;white-space:pre-wrap}}.table{{overflow:auto}}a{{color:#145ca4}}p{{overflow-wrap:anywhere}}</style>
<main><h1>{esc(labels['title'])}</h1><p>{esc(value['scope'])}</p><p>{esc(labels['meaning'])}</p><p>{esc(labels['inventory_complete'] if result['inventory_complete'] else labels['inventory_partial'])}</p><div class="table"><table><thead><tr>{''.join('<th>'+esc(c)+'</th>' for c in labels['columns'])}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h2>{esc(labels['sources'])}</h2><ul>{''.join(register)}</ul><h2>{esc(labels['limits'])}</h2><ul>{''.join('<li>'+esc(item)+'</li>' for item in result['limitations'])}</ul>
<h2>{esc(labels['privacy_title'])}</h2><p>{esc(labels['privacy'])}</p></main></html>"""
    target.write_text(page, encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("scaffold", "render"))
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--document", action="append", default=[])
    parser.add_argument("--scope", default="")
    parser.add_argument("--language", default="it")
    parser.add_argument("--review", type=Path)
    args = parser.parse_args(argv)
    try:
        target = (
            scaffold(args.run_dir, args.document, args.scope, args.language)
            if args.command == "scaffold"
            else render_citations(
                args.run_dir, args.review or args.run_dir / "citations.json"
            )
        )
        LOGGER.info("%s", target)
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        LOGGER.error("%s", error)
        return 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())

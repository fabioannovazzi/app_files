"""Run website teaching sources through the current local website workflow.

The fixture's brief and HTML are explicitly authored interpretations of these
fictional sources. Helpers snapshot, bind and check the actual output bytes.
No screenshot, professional approval, publication or learner result is forged.
"""

from __future__ import annotations

import hashlib
import html
import importlib.util
import json
from pathlib import Path

import pytest

from tests.plugins._teaching_release import record_native_check

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "plugins/presenza-digitale-studio"
LABELS = {
    "it": (
        "Sito didattico locale · studio fittizio",
        "Attività",
        "Contatti",
        "Piccole imprese italiane",
        "Segreteria",
        "Lunedì–giovedì",
        "Venerdì",
        "Scrivi alla segreteria",
    ),
    "en": (
        "Local teaching site · fictional firm",
        "Activities",
        "Contact",
        "Small Italian businesses",
        "Reception",
        "Monday–Thursday",
        "Friday",
        "Email reception",
    ),
    "fr": (
        "Site pédagogique local · cabinet fictif",
        "Activités",
        "Contact",
        "Petites entreprises italiennes",
        "Secrétariat",
        "Lundi–jeudi",
        "Vendredi",
        "Écrire au secrétariat",
    ),
    "de": (
        "Lokale Übungswebsite · fiktive Kanzlei",
        "Tätigkeiten",
        "Kontakt",
        "Kleine italienische Unternehmen",
        "Sekretariat",
        "Montag–Donnerstag",
        "Freitag",
        "Sekretariat kontaktieren",
    ),
    "es": (
        "Sitio didáctico local · despacho ficticio",
        "Actividades",
        "Contacto",
        "Pequeñas empresas italianas",
        "Secretaría",
        "Lunes–jueves",
        "Viernes",
        "Escribir a secretaría",
    ),
}
INTRO = {
    "vera": {
        "it": "Studio contabile per piccole imprese italiane.",
        "en": "Accounting practice for small Italian businesses.",
        "fr": "Cabinet comptable pour les petites entreprises italiennes.",
        "de": "Buchhaltungs- und Steuerkanzlei für kleine italienische Unternehmen.",
        "es": "Despacho contable para pequeñas empresas italianas.",
    },
    "lucia": {
        "it": "Studio legale per piccole imprese italiane.",
        "en": "Law firm for small Italian businesses.",
        "fr": "Cabinet juridique pour les petites entreprises italiennes.",
        "de": "Rechtsanwaltskanzlei für kleine italienische Unternehmen.",
        "es": "Despacho jurídico para pequeñas empresas italianas.",
    },
}
CSS = """@font-face{font-family:Instrument;src:url('InstrumentSans-Regular.ttf')}
@font-face{font-family:Instrument;src:url('InstrumentSans-SemiBold.ttf');font-weight:600}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;color:#17304e;background:#fff;font:18px/1.6 Instrument,Arial,sans-serif}a{color:inherit;text-underline-offset:.22em}a:focus-visible{outline:3px solid #127baf;outline-offset:5px}header,main,footer{max-width:1120px;margin:auto;padding:28px 48px}header{display:flex;justify-content:space-between;gap:24px;align-items:center;border-bottom:1px solid #ced7df}nav{display:flex;gap:28px}header a{text-decoration:none}.notice{font-size:14px;letter-spacing:.02em;color:#50627a}.intro{padding:52px 0 64px;max-width:850px}h1{font-size:clamp(42px,7vw,80px);line-height:1.1;font-weight:600;letter-spacing:-.045em;margin:12px 0 22px}h2{font-size:28px;line-height:1.3;margin:0 0 20px;font-weight:600}p{margin:0 0 20px}.lead{font-size:25px;max-width:760px}.section{display:grid;grid-template-columns:1fr 2fr;gap:48px;border-top:1px solid #ced7df;padding:36px 0}.details{font-variant-numeric:tabular-nums}dl{margin:16px 0 24px}dt{font-weight:600}dd{margin:0 0 16px}.action{display:inline-block;background:#17304e;color:#fff;padding:12px 20px;text-decoration:none}footer{font-size:14px;color:#50627a;border-top:1px solid #ced7df}@media(max-width:600px){header,main,footer{padding:20px}header{align-items:flex-start;gap:16px}nav{gap:18px;font-size:16px}.intro{padding:34px 0 38px}.lead{font-size:21px}.section{grid-template-columns:1fr;gap:4px;padding:28px 0}h2{font-size:25px}.details a{overflow-wrap:anywhere}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
"""


def _write(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def _core():
    spec = importlib.util.spec_from_file_location(
        "kit_website_core", COMPONENT / "scripts/workflow_core.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execute_website_fixture(base, product, language, kit, *, stop_after="practice"):
    """Use actual kit inputs and current helpers; leave rendered review pending."""
    base.mkdir(parents=True, exist_ok=True)
    core = _core()
    workspace = base / "workspace"
    core.initialize_workspace(
        workspace,
        workspace_id=f"fictional-{product}-{language}",
        owner="Fictional teaching fixture",
        retention_owner="Fixture operator",
    )
    results = []
    predecessor = {}
    for phase in ("demo", "practice"):
        sources = [
            Path(path)
            for path in kit["source_files" if phase == "demo" else "practice_files"]
        ]
        facts = next(path for path in sources if "-studio-" in path.name)
        paragraphs = facts.read_text().strip().split("\n\n")
        # The exact authored source paragraph states the two supported services.
        # This is a fixed case interpretation, not a runtime semantic extractor.
        services = paragraphs[2].split(": ")[-1]
        services = services[0].upper() + services[1:]
        ids = {f"source-{n}": path for n, path in enumerate(sources, 1)}
        intake = {
            "schema_version": 3,
            "mode": "first_site",
            "studio": {
                "name": "Studio Arco",
                "owner": "Fictional teaching fixture",
                "language": language,
            },
            "reference_date": "2026-03-12",
            "objective": "Build the supplied fictional firm's local informational page.",
            "audiences": [LABELS[language][3]],
            "requested_pages": ["Home"],
            "existing_site": {"url": None, "platform": None},
            "selected_files": [
                {
                    "id": key,
                    "role": "studio_material",
                    "path": str(path),
                    "approved_for_website_use": True,
                }
                for key, path in ids.items()
            ],
            "confirmed_facts": [],
            "constraints": [
                "Fictional local teaching site; no real professional identity or publication approval."
            ],
            "external_routes": {
                name: {
                    "selected": False,
                    "provider": "none",
                    "destination": "",
                    "approved_by_user": False,
                }
                for name in (
                    "public_site_inspection",
                    "studio_material_connector",
                    "creative_assistance",
                    "preview_publication",
                    "final_publication",
                )
            },
        }
        run = core.prepare_run(workspace, _write(base / f"{phase}-intake.json", intake))
        statements = [
            {"id": f"fact-{n}", "statement": path.read_text(), "source_ids": [key]}
            for n, (key, path) in enumerate(ids.items(), 1)
        ]
        brief = {
            "schema_version": 2,
            "mode": "first_site",
            "evidence_summary": "Supplied fictional firm profile and, for practice, an additional opening time.",
            "observed_facts": statements,
            "source_use_plan": [
                {
                    "source_id": key,
                    "professional_purpose": "Use the exact fictional profile or hours update for this local site.",
                    "post_brief_access": "mapped_brief_only",
                    "target_material": [],
                    "reason": "The brief retains all required supplied facts; no asset or full-source reopening is needed.",
                }
                for key in ids
            ],
            "open_questions": [
                "Real professional identity, registrations, applicable notices and publication destination require a separate professional review."
            ],
            "target_audiences": [LABELS[language][3]],
            "sitemap": [
                {
                    "page_id": "home",
                    "path": "/",
                    "purpose": "Introduce this fictional firm and show activities and contact.",
                    "sections": ["Introduction", "Activities", "Contact"],
                }
            ],
            "studio_profile": [
                {
                    "field": "name",
                    "value": "Studio Arco",
                    "basis": "user_supplied",
                    "evidence_ids": ["source-1"],
                },
                {
                    "field": "visual proposal",
                    "value": "Restrained navy, white, clear type and generous spacing.",
                    "basis": "vera_default_proposal",
                    "evidence_ids": [],
                },
            ],
            "content_plan": [
                {
                    "page_id": "home",
                    "primary_message": "Firm activities and contact for the supplied audience.",
                    "primary_action": "Email the supplied fictional reception address.",
                    "required_facts": [item["id"] for item in statements],
                }
            ],
            "visual_direction": {
                "intent": "Readable professional information",
                "palette": ["navy", "white"],
                "typography": "Bundled Instrument Sans",
                "image_strategy": "No photographs or invented people.",
                "avoid": ["slogans", "unverified claims"],
            },
            "implementation": {
                "approach": "Local semantic HTML and CSS; internal workflow quality standard.",
                "skills_used": [],
                "skills_unavailable": ["frontend-design"],
            },
            "claims": [
                {
                    "claim": item["statement"],
                    "evidence_ids": item["source_ids"],
                    "status": "requires_professional_confirmation",
                }
                for item in statements
            ],
            "exclusions": [
                "publication",
                "forms",
                "portals",
                "professional compliance certification",
            ],
        }
        core.record_site_brief(
            run,
            _write(base / f"{phase}-brief.json", brief),
            provider="fixture",
            model="explicit-authored-case-interpretation",
            recorded_by="Regression fixture",
        )
        site = run / "work/site"
        notice, activity, contact, audience, reception, weekdays, friday, action = map(
            html.escape, LABELS[language]
        )
        extra = f"<dt>{friday}</dt><dd>14:00–16:00</dd>" if phase == "practice" else ""
        document = f"""<!doctype html><html lang="{language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow,noarchive"><title>Studio Arco · {contact}</title><link rel="stylesheet" href="site.css"></head><body><header><b>Studio Arco</b><nav><a href="#activities">{activity}</a><a href="#contact">{contact}</a></nav></header><main><section class="intro"><p class="notice">{notice}</p><h1>Studio Arco</h1><p class="lead">{html.escape(INTRO[product][language])}</p><a class="action" href="#contact">{contact}</a></section><section class="section" id="activities"><h2>{activity}</h2><p>{html.escape(services)}</p></section><section class="section" id="contact"><h2>{contact}</h2><div class="details"><p>{reception}<br><a href="mailto:segreteria@studio-arco.example">segreteria@studio-arco.example</a></p><dl><dt>{weekdays}</dt><dd>09:00–12:00</dd>{extra}</dl><a class="action" href="mailto:segreteria@studio-arco.example">{action}</a></div></section></main><footer>{notice}</footer></body></html>"""
        (site / "index.html").write_text(document, encoding="utf-8")
        (site / "site.css").write_text(CSS, encoding="utf-8")
        for name in (
            "InstrumentSans-Regular.ttf",
            "InstrumentSans-SemiBold.ttf",
            "OFL.txt",
        ):
            (site / name).write_bytes(
                (
                    ROOT / "plugins/_shared/vendor/modules/courseware/assets" / name
                ).read_bytes()
            )
        report = json.loads(core.validate_site(run).read_text())
        assert report["status"] == "ready", report["errors"]
        assert core.validate_run(run)["status"] != "published"
        assert all(
            path.read_bytes() == content for path, content in predecessor.items()
        )
        results.append(
            {
                "run": str(run),
                "site": str(site / "index.html"),
                "site_digest": report["site_digest"],
                "phase": phase,
            }
        )
        if phase == stop_after:
            break
        predecessor = {
            path: path.read_bytes() for path in run.rglob("*") if path.is_file()
        }
    _write(
        base / "execution.json",
        {
            "product": product,
            "language": language,
            "results": results,
            "browser_review": "pending",
            "professional_approval": False,
            "published": False,
        },
    )
    return results


@pytest.mark.parametrize("product", ["vera", "lucia"])
@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_website_kit_builds_bound_local_page_and_preserves_predecessor(
    tmp_path, monkeypatch, product, language, phase, record_property
):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from courseware.library import CourseLibrary

    kit = CourseLibrary(
        ROOT / "plugins" / product, {"presenza-digitale-studio"}
    ).render("presenza-digitale-studio", language, tmp_path / "kit")
    original = {
        path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
        for key in ("source_files", "practice_files")
        for path in kit[key]
    }
    results = execute_website_fixture(
        tmp_path / "run", product, language, kit, stop_after=phase
    )
    first = Path(results[0]["site"]).read_text()
    assert "14:00–16:00" not in first
    if phase == "practice":
        second = Path(results[1]["site"]).read_text()
        assert "14:00–16:00" in second
        assert results[0]["site_digest"] != results[1]["site_digest"]
    assert all(
        "09:00–12:00" in text and "segreteria@studio-arco.example" in text
        for text in (Path(item["site"]).read_text() for item in results)
    )
    for path, digest in original.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    for result in results:
        state = json.loads((Path(result["run"]) / "run_state.json").read_text())
        assert state["packages"] == {} and state["deliveries"] == []
        assert state["quality_assessment_digest"] is None
    record_native_check(
        record_property,
        root=ROOT,
        product=product,
        workflow="presenza-digitale-studio",
        language=language,
        phase=phase,
    )

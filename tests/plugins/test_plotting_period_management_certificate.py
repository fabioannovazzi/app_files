from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "certify_plotting_period_management.py"


def load_certificate_script():
    spec = importlib.util.spec_from_file_location(
        "certify_plotting_period_management", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_certificate_matrix_covers_every_plotting_plugin() -> None:
    certificate = load_certificate_script()

    covered_plugins = {
        case.plugin
        for case in certificate.CERTIFICATION_CASES
        if case.plugin in certificate.PLOTTING_PLUGINS
    }

    assert covered_plugins == set(certificate.PLOTTING_PLUGINS)
    assert all(case.nodeids for case in certificate.CERTIFICATION_CASES)


def test_certificate_html_renders_passed_status() -> None:
    certificate = load_certificate_script()
    results = [
        certificate.CertificationResult(
            case=case,
            passed=True,
            command=("python", "-m", "pytest", "-q", *case.nodeids),
            returncode=0,
            duration_seconds=0.01,
            stdout=".",
            stderr="",
        )
        for case in certificate.CERTIFICATION_CASES
    ]

    html = certificate.render_html(results, generated_at="2026-06-16T00:00:00Z")

    assert "Certification PASSED" in html
    for plugin in certificate.PLOTTING_PLUGINS:
        assert plugin in html

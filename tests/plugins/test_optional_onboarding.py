"""Onboarding failures must never instruct the host to block ordinary work."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from zipfile import ZipFile

import pytest

__all__: list[str] = []

ROOT = Path(__file__).resolve().parents[2]
PRODUCTS = ("vera", "clara", "lucia")


@pytest.mark.parametrize("product", PRODUCTS)
@pytest.mark.parametrize(
    "phase", ("required", "interview", "teaching", "complete", "corrupt", "denied")
)
def test_startup_allows_normal_work_for_every_onboarding_state(
    product, phase, monkeypatch, capsys
):
    class ProfileError(ValueError):
        pass

    def status():
        if phase == "corrupt":
            raise ProfileError("private profile content")
        if phase == "denied":
            raise PermissionError("private profile path")
        return {"phase": phase, "profile": "private profile content"}

    monkeypatch.setitem(
        sys.modules,
        "local_onboarding",
        types.SimpleNamespace(
            OnboardingError=ProfileError,
            Store=lambda: types.SimpleNamespace(status=status),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "local_teaching",
        types.SimpleNamespace(
            TeachingStore=lambda: types.SimpleNamespace(
                status=lambda: {"active_session": None}
            )
        ),
    )
    monkeypatch.setitem(
        sys.modules, "check_for_update", types.SimpleNamespace(main=lambda: 0)
    )
    spec = importlib.util.spec_from_file_location(
        f"{product}_optional_startup",
        ROOT / f"plugins/{product}/scripts/onboarding_session_start.py",
    )
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)

    result = hook.main()

    assert result == 0
    context = json.loads(capsys.readouterr().out)["hookSpecificOutput"][
        "additionalContext"
    ]
    assert "Onboarding is optional" in context
    assert "Continue ordinary work without onboarding" in context
    assert "Only start or resume a tutorial when the user asks" in context
    assert "private profile" not in context
    assert "before routing professional work" not in context


@pytest.mark.parametrize("product", PRODUCTS)
@pytest.mark.parametrize("surface", ("plugin", "chatgpt-upload"))
def test_packaged_entrypoints_preserve_optional_onboarding(product, surface):
    with ZipFile(
        ROOT / f"plugin_packages/{product}/{product}-{surface}.zip"
    ) as archive:
        prefix = (
            f"{product}-codex-plugin/plugins/{product}/" if surface == "plugin" else ""
        )
        skills = {
            name: archive.read(name).decode()
            for name in archive.namelist()
            if name.startswith(prefix + "skills/") and name.endswith("/SKILL.md")
        }
        router = skills[prefix + f"skills/{product}/SKILL.md"]
        assert "Onboarding is optional" in router
        for name, content in skills.items():
            if f"{product.upper()}_OPENAI_ONBOARDING_BEGIN" in content:
                assert "Onboarding is optional" in content, name
            assert "mandatory one-off local onboarding gate" not in content, name
            assert "This learning gate takes precedence" not in content, name
            assert "finish all 3–4 lessons before ordinary work" not in content, name
            assert "onboarding obbligatorio" not in content, name
        reference = archive.read(
            prefix + f"skills/{product}/references/local-onboarding.md"
        ).decode()
        assert (
            "Do not run `local_onboarding.py status` before ordinary work" in reference
        )
        assert "continue the requested professional workflow" in reference

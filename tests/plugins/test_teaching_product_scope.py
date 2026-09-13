"""Exercise product-scoped lesson planning and dispatch with isolated local state."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest
from test_desktop_teaching import PROFILE, WORKFLOWS, onboarding, teaching
from test_vera_local_onboarding import ROOT, load

OWN_WORKFLOWS = {
    **WORKFLOWS,
    "vera": ["fatture-xml-check", "journal-sampling", "variance-analysis"],
}
FOREIGN_WORKFLOWS = {
    "vera": ["reporting-engine", "apertura-pratica"],
    "clara": ["fatture-xml-check", "apertura-pratica"],
    "lucia": ["fatture-xml-check", "reporting-engine"],
}


@pytest.fixture(params=["vera", "clara", "lucia"])
def scoped_store(request, monkeypatch, tmp_path):
    product = request.param
    source = ROOT / "plugins" / product
    installed = tmp_path / "installed" / product
    shutil.copytree(source / "skills", installed / "skills")
    shutil.copytree(source / ".codex-plugin", installed / ".codex-plugin")
    state = tmp_path / "profile"
    if product == "vera":
        module = load("local_onboarding")
        monkeypatch.setattr(
            module, "__file__", str(installed / "scripts/local_onboarding.py")
        )
        monkeypatch.setitem(sys.modules, "local_onboarding", module)
        repeated_module = load("local_teaching")
        store = module.Store(state)

        def repeated():
            return repeated_module.TeachingStore(state)

    else:
        store = onboarding.Store(state, plugin_root=installed)

        def repeated():
            return teaching.TeachingStore(state, plugin_root=installed)

    store.begin()
    store.change(
        "profile",
        store.status()["revision"],
        {"profile": PROFILE, "confirmed_by_user": True},
    )
    return product, installed, store, repeated


def plan(store, workflows):
    return store.change(
        "plan",
        store.status()["revision"],
        {
            "lessons": [
                {
                    "workflow_id": wf,
                    "goal": "Learn the workflow",
                    "reason": "User request",
                }
                for wf in workflows
            ]
        },
    )


def active(scoped_store):
    product, _, store, _ = scoped_store
    workflow = OWN_WORKFLOWS[product][0]
    plan(store, OWN_WORKFLOWS[product])
    store.change(
        "pair",
        store.status()["revision"],
        {"teacher_thread_id": "teacher", "worker_thread_id": "worker"},
    )
    state = store.change("start", store.status()["revision"], {"workflow_id": workflow})
    return state["lessons"][0]


def complete(scoped_store):
    product, _, store, _ = scoped_store
    active(scoped_store)
    for workflow in OWN_WORKFLOWS[product]:
        store.change("start", store.status()["revision"], {"workflow_id": workflow})
        for phase in ("demo", "practice"):
            artifact = store.root / "lessons" / workflow / f"{phase}.txt"
            artifact.write_text(f"Synthetic participant's {phase}")
            store.change(
                phase,
                store.status()["revision"],
                {
                    "workflow_id": workflow,
                    "artifacts": [artifact.name],
                    "prompt": "Try it",
                    "review": "Synthetic test evidence",
                },
            )
        store.change(
            "finish",
            store.status()["revision"],
            {
                "workflow_id": workflow,
                "confirmed_by_user": True,
                "understanding": "Synthetic participant confirmation",
            },
        )


@pytest.mark.parametrize("foreign_index", [0, 1])
def test_foreign_lesson_is_rejected_before_inputs_or_worker_dispatch(
    scoped_store, foreign_index
):
    product, _, store, _ = scoped_store
    before = store.path.read_bytes()
    foreign = FOREIGN_WORKFLOWS[product][foreign_index]

    with pytest.raises(ValueError, match="supported operational"):
        plan(store, [foreign, *OWN_WORKFLOWS[product][1:]])

    assert store.path.read_bytes() == before
    assert not (store.root / "lessons").exists()


@pytest.mark.parametrize("foreign_index", [0, 1])
def test_foreign_repeated_lesson_does_not_create_an_example(
    scoped_store, foreign_index
):
    product, _, store, repeated = scoped_store
    complete(scoped_store)
    session = repeated()
    before = store.path.read_bytes()

    with pytest.raises(ValueError, match="supported operational"):
        session.begin(
            {
                "workflow_id": FOREIGN_WORKFLOWS[product][foreign_index],
                "title": "Foreign",
                "goal": "Teach it",
            }
        )

    assert store.path.read_bytes() == before
    assert not session.sessions.exists()


@pytest.mark.parametrize("repeated_lesson", [False, True])
def test_worker_receives_own_product_and_exact_skill_path(
    scoped_store, repeated_lesson
):
    product, installed, store, repeated = scoped_store
    workflow = OWN_WORKFLOWS[product][0]
    if repeated_lesson:
        complete(scoped_store)
        store = repeated()
        lesson = store.begin(
            {"workflow_id": workflow, "title": "Own", "goal": "Teach it"}
        )["session"]
    else:
        lesson = active(scoped_store)

    result = store.worker("worker", workflow, lesson["worker_token"])

    assert result["workflow_contract"] == {
        "plugin_id": product,
        "workflow_id": workflow,
        "plugin_root": str(installed.resolve()),
        "skill_path": str(installed.resolve() / "skills" / workflow / "SKILL.md"),
    }


@pytest.mark.parametrize("replacement", ["missing", "foreign_symlink"])
@pytest.mark.parametrize("repeated_lesson", [False, True])
def test_worker_rechecks_skill_ownership_after_lesson_starts(
    scoped_store, tmp_path, replacement, repeated_lesson
):
    product, installed, store, repeated = scoped_store
    workflow = OWN_WORKFLOWS[product][0]
    if repeated_lesson:
        complete(scoped_store)
        store = repeated()
        lesson = store.begin(
            {"workflow_id": workflow, "title": "Own", "goal": "Teach it"}
        )["session"]
    else:
        lesson = active(scoped_store)
    skill = installed / "skills" / workflow / "SKILL.md"
    skill.unlink()
    if replacement == "foreign_symlink":
        foreign = tmp_path / "another-plugin-skill.md"
        foreign.write_text("A skill from another installed plugin")
        skill.symlink_to(foreign)

    with pytest.raises(ValueError):
        store.worker("worker", workflow, lesson["worker_token"])


def test_matching_installed_name_outside_catalog_is_not_teachable(scoped_store):
    product, installed, store, _ = scoped_store
    foreign = FOREIGN_WORKFLOWS[product][0]
    skill = installed / "skills" / foreign / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text("Copied from another installed plugin")

    with pytest.raises(ValueError, match="supported operational"):
        plan(store, [foreign, *OWN_WORKFLOWS[product][1:]])


def test_shared_skill_name_uses_this_products_own_contract(scoped_store):
    product, installed, store, _ = scoped_store
    shared = "quesito-legale-fiscale" if product == "lucia" else "business-planning"
    plan(store, [shared, *OWN_WORKFLOWS[product][1:]])
    store.change(
        "pair",
        store.status()["revision"],
        {"teacher_thread_id": "teacher", "worker_thread_id": "worker"},
    )
    state = store.change("start", store.status()["revision"], {"workflow_id": shared})

    contract = store.worker("worker", shared, state["lessons"][0]["worker_token"])[
        "workflow_contract"
    ]

    assert contract["plugin_id"] == product
    assert Path(contract["skill_path"]) == installed / "skills" / shared / "SKILL.md"


def test_persisted_onboarding_cannot_authorize_a_foreign_workflow(scoped_store):
    product, _, store, _ = scoped_store
    active(scoped_store)
    state = json.loads(store.path.read_text())
    lesson = state["lessons"][0]
    foreign = FOREIGN_WORKFLOWS[product][0]
    lesson["workflow_id"] = foreign
    lesson["directory"] = str(store.root / "lessons" / foreign)
    store.path.write_text(json.dumps(state))
    before = store.path.read_bytes()

    with pytest.raises(ValueError, match="only installed"):
        store.worker("worker", foreign, lesson["worker_token"])

    assert store.path.read_bytes() == before


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
@pytest.mark.parametrize("surface", ["plugin", "chatgpt-upload"])
def test_packaged_worker_binds_own_skill_and_rejects_foreign_plan(
    product, surface, tmp_path
):
    with ZipFile(
        ROOT / f"plugin_packages/{product}/{product}-{surface}.zip"
    ) as archive:
        archive.extractall(tmp_path / "installed")
    installed = tmp_path / "installed"
    if surface == "plugin":
        installed /= f"{product}-codex-plugin/plugins/{product}"
    script = """
import json
import sys
from pathlib import Path
root, state_root, workflows, foreign, profile = sys.argv[1:]
sys.path.insert(0, str(Path(root) / 'scripts'))
from local_onboarding import Store
store = Store(Path(state_root))
store.begin()
store.change('profile', store.status()['revision'], {'profile': json.loads(profile), 'confirmed_by_user': True})
def plan(ids):
    return store.change('plan', store.status()['revision'], {'lessons': [{'workflow_id': w, 'goal': 'Learn', 'reason': 'Synthetic test'} for w in ids]})
workflows = json.loads(workflows)
before = store.path.read_bytes()
try:
    plan([foreign, *workflows[1:]])
except ValueError:
    rejected = store.path.read_bytes() == before and not (store.root / 'lessons').exists()
else:
    rejected = False
plan(workflows)
store.change('pair', store.status()['revision'], {'teacher_thread_id': 'teacher', 'worker_thread_id': 'worker'})
state = store.change('start', store.status()['revision'], {'workflow_id': workflows[0]})
handoff = store.worker('worker', workflows[0], state['lessons'][0]['worker_token'])
print(json.dumps({'foreign_rejected_without_example': rejected, 'contract': handoff['workflow_contract']}))
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(installed),
            str(tmp_path / "state"),
            json.dumps(OWN_WORKFLOWS[product]),
            FOREIGN_WORKFLOWS[product][0],
            json.dumps(PROFILE),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    returned = json.loads(result.stdout)

    assert returned["foreign_rejected_without_example"] is True
    assert returned["contract"] == {
        "plugin_id": product,
        "workflow_id": OWN_WORKFLOWS[product][0],
        "plugin_root": str(installed),
        "skill_path": str(
            installed / "skills" / OWN_WORKFLOWS[product][0] / "SKILL.md"
        ),
    }

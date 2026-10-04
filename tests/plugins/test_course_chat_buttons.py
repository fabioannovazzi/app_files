"""Real storage and MCP boundaries for course chat creation and resumption."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = {
    "vera": "fatture-xml-check",
    "clara": "reporting-engine",
    "lucia": "apertura-pratica",
}


def bridge(product, operation, args):
    """Use the real installed entry modules while keeping products isolated."""
    scripts = ROOT / "plugins" / product / "scripts"
    modules = {}
    with patch.dict(sys.modules, modules):
        for name in ("_desktop_teaching", "local_onboarding", "local_teaching"):
            spec = importlib.util.spec_from_file_location(name, scripts / f"{name}.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        from courseware.chat import CourseChats

        try:
            chats = CourseChats(Path(args["state_root"]), ROOT / "plugins" / product)
            result = (
                chats.prepare(args)
                if operation == "prepare"
                else chats.claim(args["invitation"], args["thread_id"])
            )
            return 0, result
        except (ValueError, OSError) as exc:
            return 2, {"status": "blocked", "error": str(exc)}


def setup(product, directory):
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / "plugins" / product / "scripts/local_onboarding.py"),
            "setup",
            "--state-root",
            str(directory),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(process.stdout)["course"]


@pytest.fixture(params=WORKFLOWS)
def invitation(request, tmp_path):
    product = request.param
    directory = tmp_path / product
    state = setup(product, directory)
    args = {
        "state_root": str(directory),
        "teacher_thread_id": "test-teacher",
        "workflow_id": WORKFLOWS[product],
        "title": "Synthetic course",
        "goal": "Understand the real output",
        "revision": state["revision"],
        "kind": "teaching",
    }
    code, panel = bridge(product, "prepare", args)
    assert code == 0, panel
    return product, directory, args, panel


def test_confirmed_invitation_binds_real_worker_and_reuses_session(invitation):
    product, directory, args, panel = invitation
    claim = {
        "state_root": str(directory),
        "thread_id": "test-worker",
        "invitation": panel["invitation"],
    }
    code, result = bridge(product, "claim", claim)
    assert code == 0, result
    assert result["teacher_thread_id"] == "test-teacher"
    assert result["workflow_contract"]["plugin_id"] == product
    assert result["workflow_contract"]["workflow_id"] == WORKFLOWS[product]
    assert Path(result["workflow_contract"]["skill_path"]).is_file()
    assert result["lesson"]["pair"]["worker_thread_id"] == "test-worker"
    assert "demo" not in result["lesson"]
    original = result["session_id"]
    code, repeated = bridge(product, "claim", claim)
    assert code == 0, repeated
    assert repeated["session_id"] == original
    assert repeated["lesson"]["revision"] == result["lesson"]["revision"]


def test_existing_session_offers_resume_and_preserves_progress(invitation):
    product, directory, args, panel = invitation
    _, result = bridge(
        product,
        "claim",
        {
            "state_root": str(directory),
            "thread_id": "test-worker",
            "invitation": panel["invitation"],
        },
    )
    checkpoint = directory / "teaching/sessions" / result["session_id"] / "session.json"
    before = checkpoint.read_bytes()
    code, resume = bridge(
        product,
        "prepare",
        {
            **args,
            "session_id": result["session_id"],
            "revision": result["lesson"]["revision"],
        },
    )
    assert code == 0, resume
    assert resume["action"] == "resume"
    assert resume["worker_thread_id"] == "test-worker"
    assert checkpoint.read_bytes() == before


@pytest.mark.parametrize("thread", ["test-teacher", "different-worker"])
def test_invitation_rejects_teacher_or_second_worker(invitation, thread):
    product, directory, _, panel = invitation
    if thread == "different-worker":
        bridge(
            product,
            "claim",
            {
                "state_root": str(directory),
                "thread_id": "test-worker",
                "invitation": panel["invitation"],
            },
        )
    code, result = bridge(
        product,
        "claim",
        {
            "state_root": str(directory),
            "thread_id": thread,
            "invitation": panel["invitation"],
        },
    )
    assert code == 2
    assert result["status"] == "blocked"


@pytest.mark.parametrize("mutation", ["revision", "expired", "replaced"])
def test_stale_invitation_never_starts_a_session(invitation, mutation):
    product, directory, _, panel = invitation
    path = directory / "chat-invitation.json"
    ticket = json.loads(path.read_text())
    if mutation == "revision":
        ticket["revision"] += 1
    elif mutation == "expired":
        ticket["expires"] = 0
    else:
        ticket["token"] = "replaced"
    path.write_text(json.dumps(ticket))
    code, result = bridge(
        product,
        "claim",
        {
            "state_root": str(directory),
            "thread_id": "test-worker",
            "invitation": panel["invitation"],
        },
    )
    assert code == 2
    assert result["status"] == "blocked"
    assert not (directory / "teaching/sessions").exists()


def test_unknown_workflow_is_not_accepted(invitation):
    product, _, args, _ = invitation
    code, result = bridge(product, "prepare", {**args, "workflow_id": "not-installed"})
    assert code == 2
    assert result["status"] == "blocked"


@pytest.mark.parametrize("product", WORKFLOWS)
def test_packaged_launcher_registers_native_ui_without_running_a_course(product):
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "resources/read",
            "params": {"uri": f"ui://{product}/course-chats-v1.html"},
        },
    ]
    result = subprocess.run(
        ["node", str(ROOT / "plugins" / product / "scripts/course_chat_mcp.cjs")],
        input="\n".join(json.dumps(m) for m in messages) + "\n",
        text=True,
        capture_output=True,
        check=True,
    )
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    tools = responses[1]["result"]["tools"]
    assert {tool["name"] for tool in tools} == {"course_chat_open", "course_chat_claim"}
    assert (
        tools[0]["_meta"]["ui"]["resourceUri"] == f"ui://{product}/course-chats-v1.html"
    )
    assert "Apri la chat di lavoro" in responses[2]["result"]["contents"][0]["text"]


def test_messages_use_readable_text_and_correct_native_target():
    script = ROOT / "plugins/_shared/vendor/modules/courseware/assets/chat.js"
    code = "const {courseMessage}=require(process.argv[1]); const d={product:'vera',title:'Corso',workflow_id:'fatture-xml-check',state_root:'/course',teacher_thread_id:'teacher',worker_thread_id:'worker',invitation:'opaque'}; console.log(JSON.stringify(['new','resume'].map(action=>courseMessage({...d,action}))));"
    messages = json.loads(
        subprocess.check_output(["node", "-e", code, str(script)], text=True)
    )
    assert messages[0]["_meta"]["openai/message"]["target"] == "new"
    assert messages[1]["_meta"]["openai/message"]["target"] == "active"
    assert messages[0]["content"][0]["text"].startswith("Apri la chat di lavoro")
    assert "course_chat_claim" in messages[0]["content"][0]["text"]
    assert "worker" in messages[1]["content"][0]["text"]


def test_onboarding_button_starts_only_first_unfinished_lesson(invitation):
    product, directory, args, _ = invitation
    profile_script = ROOT / "plugins" / product / "scripts/local_onboarding.py"
    workflow_sets = {
        "vera": ["fatture-xml-check", "journal-sampling", "variance-analysis"],
        "clara": ["reporting-engine", "html-deck", "deck-correction"],
        "lucia": [
            "apertura-pratica",
            "comunicazione-professionale",
            "presenza-digitale-studio",
        ],
    }
    input_file = directory.parent / "input.json"
    profile = {
        "language": "it",
        "work": "Synthetic",
        "interests": "Synthetic",
        "experience": "Synthetic",
        "preferences": "Synthetic",
    }
    input_file.write_text(json.dumps({"profile": profile, "confirmed_by_user": True}))
    process = subprocess.run(
        [
            sys.executable,
            str(profile_script),
            "profile",
            "--state-root",
            str(directory),
            "--revision",
            str(args["revision"]),
            "--input",
            str(input_file),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    state = json.loads(process.stdout)
    input_file.write_text(
        json.dumps(
            {
                "lessons": [
                    {
                        "workflow_id": wf,
                        "reason": "Synthetic request",
                        "goal": "Understand output",
                    }
                    for wf in workflow_sets[product]
                ]
            }
        )
    )
    process = subprocess.run(
        [
            sys.executable,
            str(profile_script),
            "plan",
            "--state-root",
            str(directory),
            "--revision",
            str(state["revision"]),
            "--input",
            str(input_file),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    state = json.loads(process.stdout)
    code, panel = bridge(
        product,
        "prepare",
        {**args, "kind": "onboarding", "revision": state["revision"]},
    )
    assert code == 0, panel
    code, result = bridge(
        product,
        "claim",
        {
            "state_root": str(directory),
            "thread_id": "onboarding-worker",
            "invitation": panel["invitation"],
        },
    )
    assert code == 0, result
    assert result["lesson"]["status"] == "active"
    assert result["lesson"]["workflow_id"] == WORKFLOWS[product]
    assert "demo" not in result["lesson"]


def test_invitation_denied_storage_never_binds_or_executes(invitation, monkeypatch):
    product, directory, _, panel = invitation
    from courseware.chat import CourseChats

    original = CourseChats.claim

    def deny(self, token, thread):
        def blocked(*args, **kwargs):
            raise PermissionError("Synthetic revoked folder permission")

        self.store.preflight = blocked
        return original(self, token, thread)

    monkeypatch.setattr(CourseChats, "claim", deny)
    code, result = bridge(
        product,
        "claim",
        {
            "state_root": str(directory),
            "thread_id": "test-worker",
            "invitation": panel["invitation"],
        },
    )
    assert code == 2
    assert "permission" in result["error"]
    assert not (directory / "teaching/sessions").exists()


def test_interrupted_claim_blocks_duplicate_binding(invitation):
    product, directory, _, panel = invitation
    path = directory / "chat-invitation.json"
    data = json.loads(path.read_text())
    data["claimed_thread_id"] = "test-worker"
    path.write_text(json.dumps(data))
    code, result = bridge(
        product,
        "claim",
        {
            "state_root": str(directory),
            "thread_id": "test-worker",
            "invitation": panel["invitation"],
        },
    )
    assert code == 2
    assert "interrupted" in result["error"]


def test_course_ui_confirmation_duplicate_click_and_unsupported_host():
    process = subprocess.run(
        [
            "node",
            str(ROOT / "tests/plugins/course_chat_ui.cjs"),
            str(ROOT / "plugins/_shared/vendor/modules/courseware/assets/chat.js"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    assert "checks passed" in process.stdout


def test_cowork_projection_omits_openai_chat_server():
    spec = importlib.util.spec_from_file_location(
        "course_cowork_builder", ROOT / "scripts/build_claude_plugin_zip.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {spec.name: module}):
        spec.loader.exec_module(module)
        configuration = json.dumps(
            {
                "mcpServers": {
                    "courseChats": {
                        "command": "node",
                        "args": ["./scripts/course_chat_mcp.cjs"],
                    },
                    "existing": {"command": "node", "args": ["./mcp/server.cjs"]},
                }
            }
        ).encode()
        result = json.loads(module.project_claude_mcp(configuration))
    assert set(result["mcpServers"]) == {"existing"}


@pytest.mark.parametrize("product", WORKFLOWS)
def test_extracted_release_claims_course_without_repository_fallback(product, tmp_path):
    from zipfile import ZipFile

    with ZipFile(ROOT / f"plugin_packages/{product}/{product}-plugin.zip") as archive:
        archive.extractall(tmp_path / "installed")
    installed = tmp_path / f"installed/{product}-codex-plugin/plugins/{product}"
    directory = tmp_path / "course"
    setup_result = subprocess.run(
        [
            sys.executable,
            str(installed / "scripts/local_onboarding.py"),
            "setup",
            "--state-root",
            str(directory),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    state = json.loads(setup_result.stdout)["course"]
    args = {
        "state_root": str(directory),
        "teacher_thread_id": "test-teacher",
        "workflow_id": WORKFLOWS[product],
        "title": "Synthetic packaged course",
        "goal": "Understand the output",
        "revision": state["revision"],
        "kind": "teaching",
    }
    prepared = subprocess.run(
        [sys.executable, str(installed / "scripts/course_chat_bridge.py")],
        input=json.dumps({"operation": "prepare", "arguments": args}),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    invitation = json.loads(prepared.stdout)["invitation"]
    claimed = subprocess.run(
        [sys.executable, str(installed / "scripts/course_chat_bridge.py")],
        input=json.dumps(
            {
                "operation": "claim",
                "arguments": {
                    "state_root": str(directory),
                    "thread_id": "test-worker",
                    "invitation": invitation,
                },
            }
        ),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(claimed.stdout)
    assert result["workflow_contract"]["plugin_id"] == product
    assert Path(result["workflow_contract"]["skill_path"]).is_relative_to(installed)
    assert result["lesson"]["pair"]["worker_thread_id"] == "test-worker"

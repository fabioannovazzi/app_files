"""Executable safety contracts for Vera's WhatsApp Desktop search guard."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "plugins" / "studio-archive" / "scripts" / "whatsapp_desktop_guard.mjs"
REFERENCE = (
    ROOT
    / "plugins"
    / "vera"
    / "skills"
    / "studio-archive"
    / "references"
    / "whatsapp-desktop.md"
)
WRAPPER = ROOT / "plugins" / "vera" / "skills" / "studio-archive" / "SKILL.md"
MODULE_SKILL = (
    ROOT / "plugins" / "studio-archive" / "skills" / "studio-archive" / "SKILL.md"
)
PRIVACY = ROOT / "plugins" / "vera" / "privacy" / "workstreams" / "studio-archive.json"
EVALS = ROOT / "plugins" / "vera" / "evals" / "whatsapp_desktop_cases.json"
VERA_ZIP = ROOT / "plugin_packages" / "vera" / "vera-plugin.zip"


def _node_executable() -> str:
    node = shutil.which("node")
    if node is not None:
        return node
    candidates = sorted(
        (Path.home() / ".cache" / "codex-runtimes").glob("*/dependencies/node/bin/node")
    )
    if not candidates:
        pytest.skip("The Codex-bundled Node.js runtime is required.")
    return candidates[-1].as_posix()


def _accessibility_state(
    *,
    search_value: str = "",
    composer_value: str = "",
    search_focused: bool = False,
    show_send: bool = False,
    results: bool = False,
    unrelated_preview: str | None = None,
) -> str:
    search = "\t\t16 text Description: \u200eSearch"
    if search_value:
        search += f", Value: {search_value}"
    search += ", ID: TokenizedSearchBar_TextView, Secondary Actions: Cancel"
    lines = [search]
    if unrelated_preview:
        lines.append(
            "\t\t19 button Description: Other chat, "
            f"ID: ChatListRow, Value: {unrelated_preview}"
        )
    if results:
        lines.extend(
            [
                "\t\t\t23 container Description: Client Alpha, "
                "ID: ChatListSearchView_ContactResult, Secondary Actions: Cancel",
                "\t\t\t\t24 text Description: Client Alpha, "
                "ID: ChatListSearchView_ContactResult, Secondary Actions: Cancel",
                "\t\t\t30 button Description: Unrelated group, "
                "ID: ChatListSearchView_ChatResult, Value: old preview",
            ]
        )
    composer = (
        "\t\t78 text entry area Description: \u200eCompose message, "
        "ID: ChatBar_ComposerTextView, Secondary Actions: Cancel"
    )
    if composer_value:
        composer += f", Value: {composer_value}"
    lines.append(composer)
    if show_send:
        lines.append("\t\t79 button Description: Send, ID: ChatBar_SendButton")
    if search_focused:
        focused = "The focused UI element is 16 text Description: \u200eSearch"
        if search_value:
            focused += f", Value: {search_value}"
        focused += ", ID: TokenizedSearchBar_TextView, Secondary Actions: Cancel"
        lines.append(focused)
    return "\n".join(lines)


def _contact_card_state(*, phone: str = "+12 345 678") -> str:
    return "\n".join(
        [
            "  15 button Description: Profile image, "
            "ID: contact-info-header-profile-image",
            "  17 heading Description: Client Alpha",
            f"  18 text Description: {phone}",
            "  27 button Description: Done, Secondary Actions: Cancel",
        ]
    )


def _selected_chat_state(*, search_value: str, show_results: bool) -> str:
    search = "  16 text Description: Search"
    if search_value:
        search += f", Value: {search_value}"
    search += ", ID: TokenizedSearchBar_TextView, Secondary Actions: Cancel"
    lines = [search]
    if search_value:
        lines.append(
            "  18 button Description: Clear text, "
            "ID: TokenizedSearchBar_DeleteButton"
        )
    if show_results:
        lines.extend(
            [
                "  23 container Description: Client Alpha, "
                "ID: ChatListSearchView_ContactResult, Secondary Actions: "
                "Cancel, More Info",
                "    24 text Description: Client Alpha, "
                "ID: ChatListSearchView_ContactResult, Secondary Actions: "
                "Cancel, More Info",
            ]
        )
    lines.extend(
        [
            "  43 button Description: Client Alpha, "
            "ID: NavigationBar_HeaderViewButton",
            "  50 container Description: Messages in chat with Client Alpha, "
            "ID: ChatMessagesTableView",
            "    51 text Description: Target message evidence, "
            "ID: WAMessageBubbleTableViewCell",
            "  78 text entry area Description: Compose message, "
            "ID: ChatBar_ComposerTextView, Secondary Actions: Cancel",
        ]
    )
    return "\n".join(lines)


def _run_guard(
    states: list[str],
    *,
    phone: str = "+12 345 678",
    expected_name: str = "Client Alpha",
    reject_search_shortcut: bool = False,
) -> dict[str, Any]:
    scenario = {
        "states": states,
        "phone": phone,
        "expectedName": expected_name,
        "rejectSearchShortcut": reject_search_shortcut,
    }
    source = f"""
import {{ guardedPhoneSearch }} from {json.dumps(GUARD.as_uri())};
const scenario = {json.dumps(scenario)};
const calls = [];
const states = [...scenario.states];
const sky = {{
  async list_apps() {{
    calls.push({{ method: "list_apps" }});
    return [{{ id: "net.whatsapp.WhatsApp", isRunning: true }}];
  }},
  async get_app_state(args) {{
    calls.push({{ method: "get_app_state", args }});
    if (!states.length) throw new Error("Unexpected state read");
    return {{ app: args.app, screenshot: null, text: states.shift() }};
  }},
  async click(args) {{ calls.push({{ method: "click", args }}); }},
  async press_key(args) {{
    calls.push({{ method: "press_key", args }});
    if (scenario.rejectSearchShortcut && args.key === "super+f") {{
      throw new Error("Computer Use rejected modifier chord");
    }}
  }},
  async set_value(args) {{ calls.push({{ method: "set_value", args }}); }},
  async type_text(args) {{ calls.push({{ method: "type_text", args }}); }},
}};
const result = await guardedPhoneSearch({{
  sky,
  confirmedPhone: scenario.phone,
  expectedChatName: scenario.expectedName,
}});
console.log(JSON.stringify({{ result, calls, remainingStates: states.length }}));
"""
    completed = subprocess.run(
        [_node_executable(), "--input-type=module", "--eval", source],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return json.loads(completed.stdout)


def _run_guard_and_open(states: list[str]) -> dict[str, Any]:
    source = f"""
import {{
  guardedPhoneSearch,
  verifyAndOpenGuardedTarget,
}} from {json.dumps(GUARD.as_uri())};
const states = {json.dumps(states)};
const calls = [];
const sky = {{
  async list_apps() {{
    calls.push({{ method: "list_apps" }});
    return [{{ id: "net.whatsapp.WhatsApp", isRunning: true }}];
  }},
  async get_app_state(args) {{
    calls.push({{ method: "get_app_state", args }});
    if (!states.length) throw new Error("Unexpected state read");
    return {{ app: args.app, screenshot: null, text: states.shift() }};
  }},
  async click(args) {{ calls.push({{ method: "click", args }}); }},
  async press_key(args) {{ calls.push({{ method: "press_key", args }}); }},
  async set_value(args) {{ calls.push({{ method: "set_value", args }}); }},
  async type_text(args) {{ calls.push({{ method: "type_text", args }}); }},
  async perform_secondary_action(args) {{
    calls.push({{ method: "perform_secondary_action", args }});
  }},
}};
const search = await guardedPhoneSearch({{
  sky,
  confirmedPhone: "+12 345 678",
  expectedChatName: "Client Alpha",
}});
const opened = await verifyAndOpenGuardedTarget({{
  sky,
  searchResult: search,
  confirmedPhone: "+12 345 678",
  expectedChatName: "Client Alpha",
}});
console.log(JSON.stringify({{ search, opened, calls, remainingStates: states.length }}));
"""
    completed = subprocess.run(
        [_node_executable(), "--input-type=module", "--eval", source],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return json.loads(completed.stdout)


def test_guard_enters_phone_one_digit_at_a_time_and_returns_one_target() -> None:
    phone_digits = "12345678"
    states = [
        _accessibility_state(),
        _accessibility_state(search_focused=True),
        _accessibility_state(search_focused=True),
        *[
            _accessibility_state(
                search_value=phone_digits[:length],
                search_focused=True,
                results=length == len(phone_digits),
                unrelated_preview="PRIVATE OTHER CLIENT PREVIEW",
            )
            for length in range(1, len(phone_digits) + 1)
        ],
    ]

    observed = _run_guard(states)

    result = observed["result"]
    key_calls = [
        call["args"]["key"]
        for call in observed["calls"]
        if call["method"] == "press_key"
    ]
    assert result == {
        "status": "ready_to_open_target",
        "reason": None,
        "digitsEntered": len(phone_digits),
        "composerEmpty": True,
        "cleanup": "not_needed",
        "targetResult": {
            "elementIndex": 23,
            "kind": "contact",
            "matchedBy": "exact_confirmed_identity",
        },
        "resultCount": 2,
        "contactResultCount": 1,
    }
    assert key_calls == ["super+f", *phone_digits]
    assert observed["remainingStates"] == 0
    assert all(call["method"] != "type_text" for call in observed["calls"])
    assert "Return" not in json.dumps(observed)
    assert "PRIVATE OTHER CLIENT PREVIEW" not in json.dumps(result)


def test_guard_removes_only_one_proven_misdirected_digit_then_stops() -> None:
    states = [
        _accessibility_state(),
        _accessibility_state(search_focused=True),
        _accessibility_state(search_focused=True),
        _accessibility_state(search_value="1", search_focused=True),
        _accessibility_state(
            search_value="1",
            composer_value="2",
            show_send=True,
        ),
        _accessibility_state(search_value="1"),
    ]

    observed = _run_guard(states)

    result = observed["result"]
    set_calls = [call for call in observed["calls"] if call["method"] == "set_value"]
    key_calls = [
        call["args"]["key"]
        for call in observed["calls"]
        if call["method"] == "press_key"
    ]
    assert result["status"] == "blocked"
    assert result["reason"] == "misdirected_digit_removed"
    assert result["digitsEntered"] == 1
    assert result["composerEmpty"] is True
    assert result["cleanup"] == "completed"
    assert set_calls == [
        {
            "method": "set_value",
            "args": {
                "app": "net.whatsapp.WhatsApp",
                "element_index": 78,
                "value": "",
            },
        }
    ]
    assert key_calls == ["super+f", "1", "2"]
    assert "3" not in key_calls


def test_guard_uses_the_exact_prefix_when_focus_metadata_is_absent() -> None:
    phone_digits = "12345678"
    states = [
        _accessibility_state(),
        _accessibility_state(),
        _accessibility_state(),
        *[
            _accessibility_state(
                search_value=phone_digits[:length],
                results=length == len(phone_digits),
            )
            for length in range(1, len(phone_digits) + 1)
        ],
    ]

    observed = _run_guard(states)

    assert observed["result"]["status"] == "ready_to_open_target"
    assert observed["result"]["digitsEntered"] == len(phone_digits)
    assert observed["result"]["composerEmpty"] is True


def test_guard_clicks_fresh_empty_search_when_shortcut_is_rejected() -> None:
    phone_digits = "12345678"
    states = [
        _accessibility_state(),
        _accessibility_state(),
        _accessibility_state(search_focused=True),
        *[
            _accessibility_state(
                search_value=phone_digits[:length],
                search_focused=True,
                results=length == len(phone_digits),
            )
            for length in range(1, len(phone_digits) + 1)
        ],
    ]

    observed = _run_guard(states, reject_search_shortcut=True)

    assert observed["result"]["status"] == "ready_to_open_target"
    assert observed["result"]["digitsEntered"] == len(phone_digits)
    assert observed["result"]["composerEmpty"] is True
    assert [
        call["args"]["element_index"]
        for call in observed["calls"]
        if call["method"] == "click"
    ] == [16]


def test_guard_stops_if_controls_change_after_shortcut_rejection() -> None:
    states = [
        _accessibility_state(),
        _accessibility_state(composer_value="unexpected draft", show_send=True),
    ]

    observed = _run_guard(states, reject_search_shortcut=True)

    assert observed["result"]["status"] == "blocked"
    assert observed["result"]["reason"] == "search_focus_not_proven"
    assert observed["result"]["digitsEntered"] == 0
    assert observed["result"]["composerEmpty"] is False
    assert all(call["method"] != "click" for call in observed["calls"])
    assert all(
        call["args"].get("key") == "super+f"
        for call in observed["calls"]
        if call["method"] == "press_key"
    )


def test_guard_verifies_more_info_before_opening_only_the_exact_chat() -> None:
    phone_digits = "12345678"
    states = [
        _accessibility_state(),
        _accessibility_state(search_focused=True),
        _accessibility_state(search_focused=True),
        *[
            _accessibility_state(
                search_value=phone_digits[:length],
                search_focused=True,
                results=length == len(phone_digits),
                unrelated_preview="PRIVATE OTHER CLIENT PREVIEW",
            )
            for length in range(1, len(phone_digits) + 1)
        ],
        _contact_card_state(),
        _accessibility_state(search_value=phone_digits, results=True),
        _selected_chat_state(search_value=phone_digits, show_results=True),
        _selected_chat_state(search_value="", show_results=False),
    ]

    observed = _run_guard_and_open(states)

    assert observed["search"]["status"] == "ready_to_open_target"
    assert observed["opened"] == {
        "status": "verified_target_open",
        "reason": None,
        "phoneVerified": True,
        "composerEmpty": True,
        "targetTableAvailable": True,
    }
    assert observed["remainingStates"] == 0
    secondary_calls = [
        call
        for call in observed["calls"]
        if call["method"] == "perform_secondary_action"
    ]
    click_indices = [
        call["args"]["element_index"]
        for call in observed["calls"]
        if call["method"] == "click"
    ]
    assert secondary_calls == [
        {
            "method": "perform_secondary_action",
            "args": {
                "app": "net.whatsapp.WhatsApp",
                "element_index": 23,
                "action": "More Info",
            },
        }
    ]
    assert click_indices == [16, 27, 23, 18]
    assert all(call["method"] != "type_text" for call in observed["calls"])
    assert "Return" not in json.dumps(observed)
    assert "PRIVATE OTHER CLIENT PREVIEW" not in json.dumps(
        {"search": observed["search"], "opened": observed["opened"]}
    )


def test_guard_does_not_open_a_contact_card_with_the_wrong_phone() -> None:
    phone_digits = "12345678"
    states = [
        _accessibility_state(),
        _accessibility_state(search_focused=True),
        _accessibility_state(search_focused=True),
        *[
            _accessibility_state(
                search_value=phone_digits[:length],
                search_focused=True,
                results=length == len(phone_digits),
            )
            for length in range(1, len(phone_digits) + 1)
        ],
        _contact_card_state(phone="+87 654 321"),
    ]

    observed = _run_guard_and_open(states)

    assert observed["search"]["status"] == "ready_to_open_target"
    assert observed["opened"]["status"] == "blocked"
    assert observed["opened"]["reason"] == "contact_identity_not_verified"
    assert observed["opened"]["phoneVerified"] is False
    click_indices = [
        call["args"]["element_index"]
        for call in observed["calls"]
        if call["method"] == "click"
    ]
    assert click_indices == [16, 27]


def test_guard_preserves_a_preexisting_composer_draft() -> None:
    states = [
        _accessibility_state(composer_value="existing draft", show_send=True),
    ]

    observed = _run_guard(states)

    assert observed["result"]["status"] == "blocked"
    assert observed["result"]["reason"] == "search_or_composer_not_empty"
    assert observed["result"]["composerEmpty"] is False
    assert [call["method"] for call in observed["calls"]] == [
        "list_apps",
        "get_app_state",
    ]


def test_guard_does_not_clear_an_unknown_composer_transition() -> None:
    states = [
        _accessibility_state(),
        _accessibility_state(search_focused=True),
        _accessibility_state(search_focused=True),
        _accessibility_state(
            composer_value="unknown content",
            show_send=True,
        ),
    ]

    observed = _run_guard(states)

    assert observed["result"]["status"] == "blocked"
    assert observed["result"]["reason"] == "unsafe_text_transition"
    assert observed["result"]["cleanup"] == "not_attempted_unknown_content"
    assert all(call["method"] != "set_value" for call in observed["calls"])


def test_verified_chat_extraction_excludes_sidebar_and_composer() -> None:
    state = "\n".join(
        [
            "  10 button Description: Other chat, Value: PRIVATE SIDEBAR PREVIEW",
            "  50 container Description: Messages in chat with Client Alpha, "
            "ID: ChatMessagesTableView",
            "    51 text Description: Target message evidence",
            "  78 text entry area Description: Compose message, "
            "ID: ChatBar_ComposerTextView",
        ]
    )
    source = f"""
import {{ extractVerifiedChatTable }} from {json.dumps(GUARD.as_uri())};
const state = {json.dumps(state)};
const verified = extractVerifiedChatTable(state, {{
  expectedChatName: "Client Alpha",
  phoneVerified: true,
}});
const unverified = extractVerifiedChatTable(state, {{
  expectedChatName: "Client Alpha",
  phoneVerified: false,
}});
console.log(JSON.stringify({{ verified, unverified }}));
"""

    completed = subprocess.run(
        [_node_executable(), "--input-type=module", "--eval", source],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    observed = json.loads(completed.stdout)

    assert "Target message evidence" in observed["verified"]
    assert "PRIVATE SIDEBAR PREVIEW" not in observed["verified"]
    assert "Compose message" not in observed["verified"]
    assert observed["unverified"] is None


def test_source_contracts_require_the_executable_guard_and_private_state() -> None:
    reference = " ".join(REFERENCE.read_text(encoding="utf-8").split())
    wrapper = " ".join(WRAPPER.read_text(encoding="utf-8").split())
    module_skill = " ".join(MODULE_SKILL.read_text(encoding="utf-8").split())
    privacy = json.loads(PRIVACY.read_text(encoding="utf-8"))
    evals = json.loads(EVALS.read_text(encoding="utf-8"))
    guard_source = GUARD.read_text(encoding="utf-8")
    boundary = next(
        item
        for item in privacy["external_boundaries"]
        if item["id"] == "codex-whatsapp-desktop-client-review"
    )
    controls = " ".join(boundary["controls"])

    for source in (reference, module_skill):
        assert "guardedPhoneSearch" in source
        assert "verifyAndOpenGuardedTarget" in source
        assert "one digit at a time" in source
        assert "Never use `type_text`" in source
        assert "raw pre-verification accessibility state" in source.casefold()
        assert "extractVerifiedChatTable" in source
    assert "whatsapp_desktop_guard.mjs" in wrapper
    assert "any other WhatsApp script" in wrapper
    assert "one digit at a time" in controls
    assert "Raw pre-verification accessibility snapshots" in boundary["content"]
    assert evals["version"] == 2
    assert "await sky.type_text" not in guard_source
    assert 'key: "Return"' not in guard_source
    assert "await sky.set_value" in guard_source
    assert 'action: "More Info"' in guard_source
    assert "TokenizedSearchBar_DeleteButton" in guard_source


def test_vera_package_contains_the_exact_guard_source() -> None:
    guard_entry = (
        "vera-codex-plugin/plugins/vera/modules/studio-archive/"
        "scripts/whatsapp_desktop_guard.mjs"
    )
    reference_entry = (
        "vera-codex-plugin/plugins/vera/skills/studio-archive/"
        "references/whatsapp-desktop.md"
    )

    with ZipFile(VERA_ZIP) as archive:
        packaged_guard = archive.read(guard_entry)
        packaged_reference = archive.read(reference_entry).decode("utf-8")

    assert packaged_guard == GUARD.read_bytes()
    assert "verifyAndOpenGuardedTarget" in packaged_reference

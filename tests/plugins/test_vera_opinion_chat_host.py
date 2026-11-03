"""Opt-in regression against a real, locally installed Vera in an ephemeral Codex turn."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []


@pytest.mark.skipif(
    os.environ.get("VERA_OPINION_HOST_TEST") != "1" or shutil.which("codex") is None,
    reason="Needs an authenticated Codex installation with the candidate Vera enabled",
)
@pytest.mark.parametrize("entry", ["specialist", "vera"])
def test_question_and_planned_sources_reach_chat_before_first_lookup(tmp_path, entry):
    # These are fictional authorities. Their unexpected values establish that
    # the host actually opened them after announcing the plan.
    (tmp_path / "Aurora.md").write_text(
        "Convenzione Aurora (fittizia), articolo 4. Il deposito scade il diciassettesimo giorno.\n"
    )
    (tmp_path / "Vega.md").write_text(
        "Protocollo Vega (fittizio), articolo 2. Solo la chiusura dello sportello proroga il termine di sei giorni.\n"
    )
    task = (
        "Esercizio sintetico standalone. Qual è il termine per il deposito e quando si proroga? "
        "Le sole autorità del caso fittizio sono Convenzione Aurora (Aurora.md) e Protocollo Vega (Vega.md), "
        "in questa cartella. Non usare fonti esterne, un cliente reale o servizi esterni."
    )
    if entry == "specialist":
        prompt = (
            "Usa la Vera installata e il suo percorso quesito-legale-fiscale. "
            + task
            + " Fermati dopo aver consultato le due fonti. Dammi un riscontro breve in chat, "
            "senza fascicolo finale né parere contrapposto."
        )
    else:
        prompt = (
            "Usa la Vera installata per un breve parere in italiano. "
            + task
            + " Produci il parere in Markdown nella cartella di questo esercizio. "
            "Non serve il parere contrapposto."
        )
    transcript = tmp_path / "codex-events.jsonl"
    # The installed managed interpreter takes a lease while packaging an
    # opinion. Give this ephemeral host its normal runtime capability without
    # expanding the writable scope to other user or client directories.
    runtime = Path(
        os.environ.get(
            "MPARANZA_RUNTIME_ROOT", Path.home() / ".local/share/mparanza/runtime"
        )
    )
    runtime_scope = ["--add-dir", str(runtime)] if runtime.is_dir() else []
    with transcript.open("w", encoding="utf-8") as stream:
        result = subprocess.run(
            [
                "codex",
                "exec",
                "--ephemeral",
                "--json",
                "--sandbox",
                "workspace-write",
                *runtime_scope,
                "--skip-git-repo-check",
                "--cd",
                str(tmp_path),
                "-",
            ],
            input=prompt,
            stdout=stream,
            stderr=subprocess.PIPE,
            text=True,
            timeout=950,
        )
    assert result.returncode == 0, result.stderr[-1200:]
    trace = transcript.read_text()
    events = [json.loads(line) for line in trace.splitlines() if line.startswith("{")]
    items = [(i, e.get("type"), e.get("item", {})) for i, e in enumerate(events)]
    manifest = (
        Path(__file__).resolve().parents[2] / "plugins/vera/.codex-plugin/plugin.json"
    )
    version = json.loads(manifest.read_text())["version"]
    assert (
        f"/vera/{version}/skills/" in trace
    ), f"Release skill was not observed: {transcript}"
    preview = [
        i
        for i, kind, item in items
        if kind == "item.completed"
        and item.get("type") == "agent_message"
        and all(
            word in item.get("text", "").casefold()
            for word in ("deposit", "prorog", "aurora", "vega")
        )
    ]
    # Listing filenames does not disclose either authority. Locate the first
    # tool operation whose result actually contained a fixture's source text,
    # then compare its start event with the already-visible assistant message.
    content_ids = {
        item["id"]
        for _, kind, item in items
        if kind == "item.completed"
        and item.get("type") in {"command_execution", "mcp_tool_call"}
        and any(
            marker in json.dumps(item, ensure_ascii=False).casefold()
            for marker in (
                "scade il diciassettesimo giorno",
                "chiusura dello sportello proroga il termine",
            )
        )
    }
    reads = [
        i
        for i, kind, item in items
        if kind == "item.started" and item.get("id") in content_ids
    ]
    assert (
        reads and preview and min(preview) < min(reads)
    ), f"Missing pre-research chat preview: {transcript}"
    final = [
        item["text"]
        for i, kind, item in items
        if i > min(reads)
        and kind == "item.completed"
        and item.get("type") == "agent_message"
    ][-1]
    if entry == "specialist":
        presented = final.lower()
    else:
        opinions = list(tmp_path.rglob("validated_document.md"))
        assert opinions, f"No packaged opinion delivered: {transcript}"
        product = Path.home() / ".codex/plugins/cache/mp-vera/vera" / version
        for opinion in opinions:
            subprocess.run(
                [
                    sys.executable,
                    str(product / "scripts/opinion_validation.py"),
                    "verify",
                    str(opinion.parent),
                ],
                check=True,
            )
        linked = [
            (tmp_path / link).resolve()
            for link in re.findall(r"\]\(([^)]+\.md)\)", final)
        ]
        delivered = [
            path.read_text()
            for path in linked
            if path.is_relative_to(tmp_path.resolve()) and path.is_file()
        ]
        assert any(
            opinion.read_text().strip() == text.strip()
            for opinion in opinions
            for text in delivered
        ), final
        presented = opinions[0].read_text().lower()
    paragraphs = [p for p in presented.split("\n") if p.strip()]
    assert any(
        re.search(r"17|diciassett", p) and "aurora" in p for p in paragraphs
    ), presented
    assert any(
        re.search(r"\b6\b|\bsei\b", p) and "vega" in p for p in paragraphs
    ), presented

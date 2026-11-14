"""Assignment continuity over real ledger files, with preserved source bytes."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tests.plugins.test_vera_client_workflow_filesystem import (
    VERA_CLIENT_WORKFLOW_IDS,
    _completed_context,
    _load_customer_ledger,
    load_client_engagement_context_file,
)

CLIENT = "client_123456789012345678901234"
PUBLIC_PIPELINES = tuple(
    json.loads(
        (
            Path(__file__).resolve().parents[2] / "plugins/vera/usage/pipelines.json"
        ).read_text()
    )["pipelines"]
)


@pytest.fixture
def assignment(tmp_path):
    ledger = _load_customer_ledger()
    root = tmp_path / "Eutekne"
    root.mkdir()
    ledger.create_client_manifest(root, CLIENT)
    engagement = ledger.create_engagement(root, CLIENT, "E26-01")
    identifier = engagement["engagement_id"]
    receipts = []
    for name, role in (
        ("Incarico.md", "support"),
        ("Quesito.txt", "source"),
        ("Parere.md", "support"),
    ):
        path = tmp_path / name
        path.write_text(f"Synthetic {name}: più informazioni", encoding="utf-8")
        receipts.append(
            ledger.import_document(root, CLIENT, identifier, path, role)["receipt"]
        )
    return ledger, root, identifier, receipts


def fields(receipts, workflow="quesito-legale-fiscale"):
    return {
        "workflow_id": workflow,
        "purpose": "Preparare il parere richiesto",
        "continuation": "Parere salvato; eventuali nuovi documenti richiedono una nuova versione.",
        "results": [
            {
                "reference": {"input_id": receipts[-1]["input_id"]},
                "label": "Parere",
                "sha256": receipts[-1]["sha256"],
            }
        ],
        "conversations": [],
    }


def preserved(root: Path):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_document_only_assignment_is_visible_without_creating_a_run(assignment):
    ledger, root, identifier, receipts = assignment
    before = preserved(root)
    view = ledger.incarichi().overview(root, identifier)
    assert [row["name"] for row in view["documents"]] == [
        r["original_name"] for r in receipts
    ]
    assert view["workflow_id"] is None
    assert preserved(root) == before
    assert ledger.list_runs(root, identifier) == ()


def test_saved_opinion_is_a_result_without_rewriting_its_support_receipt(assignment):
    ledger, root, identifier, receipts = assignment
    before = preserved(root)
    saved = ledger.incarichi().update(root, identifier, fields(receipts), "")
    view = ledger.incarichi().overview(root, identifier)
    assert view["results"][0]["available"] is True
    assert view["revision"] == saved["revision"]
    assert (
        ledger.load_input_receipt(root, identifier, receipts[-1]["input_id"])["role"]
        == "support"
    )
    assert {name: preserved(root)[name] for name in before} == before
    assert ledger.list_runs(root, identifier) == ()


def test_exact_retry_does_not_create_history_and_stale_edit_cannot_overwrite(
    assignment,
):
    ledger, root, identifier, receipts = assignment
    store = ledger.incarichi()
    first = store.update(root, identifier, fields(receipts), "")
    before = preserved(root)
    assert store.update(root, identifier, fields(receipts), "") == first
    assert preserved(root) == before
    changed = {**fields(receipts), "continuation": "Nuova domanda ricevuta"}
    second = store.update(root, identifier, changed, first["revision"])
    with pytest.raises(ledger.LedgerError, match="another chat"):
        store.update(
            root,
            identifier,
            {**changed, "continuation": "Stale replacement"},
            first["revision"],
        )
    history = root / "Vera" / "engagements" / identifier / "incarico-history"
    assert (history / f"{first['revision']}.json").is_file()
    assert store.read(root, identifier)["revision"] == second["revision"]


def test_concurrent_chats_retain_one_winner_without_losing_the_original(assignment):
    ledger, root, identifier, receipts = assignment
    store = ledger.incarichi()
    first = store.update(root, identifier, fields(receipts), "")

    def save(note):
        try:
            store.update(
                root,
                identifier,
                {**fields(receipts), "continuation": note},
                first["revision"],
            )
            return "saved"
        except ledger.LedgerError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(save, ["First continuation", "Second continuation"]))
    assert sorted(outcomes) == ["conflict", "saved"]
    assert (
        ledger.load_input_receipt(root, identifier, receipts[-1]["input_id"])["sha256"]
        == receipts[-1]["sha256"]
    )


def test_bound_assignment_refuses_unrelated_pipeline_before_run_creation(assignment):
    ledger, root, identifier, receipts = assignment
    ledger.incarichi().update(root, identifier, fields(receipts), "")
    with pytest.raises(ledger.LedgerError, match="different purpose/workflow"):
        ledger.prepare_run(
            root,
            CLIENT,
            identifier,
            "business-planning",
            "0.1.0",
            input_ids=[receipts[0]["input_id"]],
        )
    assert ledger.list_runs(root, identifier) == ()


def test_legal_answer_stages_remain_inside_the_same_assignment(assignment):
    ledger, root, identifier, receipts = assignment
    ledger.incarichi().update(root, identifier, fields(receipts), "")
    run = ledger.prepare_run(
        root,
        CLIENT,
        identifier,
        "deep-research-validator",
        "0.1.0",
        input_ids=[receipts[0]["input_id"]],
    )
    assert run["run"]["engagement_id"] == identifier


def test_other_assignment_document_cannot_be_adopted_as_result(assignment, tmp_path):
    ledger, root, identifier, receipts = assignment
    other = ledger.create_engagement(root, CLIENT, "Other assignment")
    path = tmp_path / "other.md"
    path.write_text("Other result", encoding="utf-8")
    receipt = ledger.import_document(
        root, CLIENT, other["engagement_id"], path, "support"
    )["receipt"]
    with pytest.raises(ledger.LedgerError):
        ledger.incarichi().update(root, identifier, fields([receipt]), "")
    assert ledger.incarichi().read(root, identifier)["revision"] == ""


def test_changed_saved_document_is_unavailable_without_hiding_the_case(assignment):
    ledger, root, identifier, receipts = assignment
    store = ledger.incarichi()
    saved = store.update(root, identifier, fields(receipts), "")
    document = store.document(root, identifier, saved["results"][0]["reference"])
    Path(document["path"]).write_text("changed bytes", encoding="utf-8")
    view = store.overview(root, identifier)
    assert view["results"][0]["available"] is False
    assert len(view["documents"]) == 2
    assert len(view["document_issues"]) == 1


def test_bilancio_output_can_feed_a_separate_business_plan_with_exact_origin(tmp_path):
    context_path, _, output, source_run = _completed_context(
        tmp_path, "bilancio-xbrl-it"
    )
    ledger = _load_customer_ledger()
    source_context = json.loads(context_path.read_text(encoding="utf-8"))
    root = context_path.parents[5]
    before = preserved(root)
    target = ledger.create_engagement(
        root, source_context["client_id"], "Business plan"
    )
    reference = {
        "engagement_id": source_context["engagement_id"],
        "run_id": source_run,
        "artifact_id": "prepared.result",
        "role": "historical_accounts",
    }
    prepared = ledger.prepare_run(
        root,
        source_context["client_id"],
        target["engagement_id"],
        "business-planning",
        "test-version",
        upstream_artifacts=[reference],
        idempotency_key="bilancio-to-business-plan",
    )
    binding = prepared["context"]["input_bindings"][0]
    assert binding["upstream_engagement_id"] == source_context["engagement_id"]
    assert binding["upstream_run_id"] == source_run
    assert Path(binding["path"]).read_bytes() == (output / "result.txt").read_bytes()
    assert {name: preserved(root)[name] for name in before} == before
    ledger.start_run(root, target["engagement_id"], prepared["run"]["run_id"])
    hydrated = load_client_engagement_context_file(
        Path(prepared["context_path"]), expected_workflow_id="business-planning"
    )
    assert (
        hydrated["input_bindings"][0]["upstream_engagement_id"]
        == source_context["engagement_id"]
    )
    retry = ledger.prepare_run(
        root,
        source_context["client_id"],
        target["engagement_id"],
        "business-planning",
        "test-version",
        upstream_artifacts=[reference],
        idempotency_key="bilancio-to-business-plan",
    )
    assert retry["run"]["run_id"] == prepared["run"]["run_id"]
    (output / "result.txt").write_text("Later changed source", encoding="utf-8")
    reopened = ledger.load_run(root, target["engagement_id"], prepared["run"]["run_id"])
    assert (
        Path(reopened["context"]["input_bindings"][0]["path"]).read_text(
            encoding="utf-8"
        )
        == "reviewable result\n"
    )
    with pytest.raises(ledger.LedgerError):
        ledger.prepare_run(
            root,
            source_context["client_id"],
            target["engagement_id"],
            "business-planning",
            "test-version",
            upstream_artifacts=[reference],
            idempotency_key="changed-bilancio",
        )


def publish_files(tmp_path, text="First revision"):
    files = []
    for extension in ("md", "pdf"):
        path = tmp_path / f"Parere.{extension}"
        path.write_bytes(text.encode())
        files.append(
            {
                "format": extension,
                "source_path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return files


def test_current_result_groups_formats_and_retains_numbered_history(
    assignment, tmp_path
):
    ledger, root, eid, receipts = assignment
    store = ledger.incarichi()
    store.update(root, eid, fields(receipts), "")
    before = preserved(root)
    files = publish_files(tmp_path)
    first = ledger.deliverables().publish(
        root, eid, "opinion", "Parere", files, 0, "save-1"
    )
    assert (
        ledger.deliverables().publish(
            root, eid, "opinion", "Parere", files, 0, "save-1"
        )["reused"]
        is True
    )
    assert len(ledger.list_inputs(root, eid)) == 3
    assert {name: preserved(root)[name] for name in before} == before
    second = ledger.deliverables().publish(
        root,
        eid,
        "opinion",
        "Parere",
        publish_files(tmp_path, "Second revision"),
        1,
        "save-2",
    )
    entry = store.overview(root, eid)["deliverables"][0]
    assert entry["current_revision"] == 2
    assert len(entry["versions"]) == 2
    assert all(len(v["formats"]) == 2 and v["issued_at"] for v in entry["versions"])
    old = store.document(
        root, eid, {"entry_key": "opinion", "revision": 1, "format": "md"}
    )
    assert Path(old["path"]).read_text() == "First revision"
    # A delayed retry of an earlier save cannot move the current pointer back.
    retry = ledger.deliverables().publish(
        root, eid, "opinion", "Parere", files, 0, "save-1"
    )
    assert retry["issued"] == first["issued"]
    assert retry["current_revision"] == second["current_revision"] == 2
    assert ledger.list_runs(root, eid) == ()


def test_interrupted_group_copy_never_publishes_half_a_result(
    assignment, tmp_path, monkeypatch
):
    ledger, root, eid, receipts = assignment
    ledger.incarichi().update(root, eid, fields(receipts), "")
    files = publish_files(tmp_path)
    original = ledger._stable_copy
    calls = []

    def fail(source, destination):
        copied = original(source, destination)
        calls.append(source)
        if len(calls) == 2:
            raise OSError("Interrupted copy")
        return copied

    monkeypatch.setattr(ledger, "_stable_copy", fail)
    with pytest.raises(OSError, match="Interrupted"):
        ledger.deliverables().publish(
            root, eid, "opinion", "Parere", files, 0, "save-1"
        )
    assert ledger.incarichi().overview(root, eid)["deliverables"] == []
    monkeypatch.setattr(ledger, "_stable_copy", original)
    assert (
        ledger.deliverables().publish(
            root, eid, "opinion", "Parere", files, 0, "save-1"
        )["current_revision"]
        == 1
    )


@pytest.mark.parametrize("standalone", [False, True])
def test_saved_result_can_cross_clients_with_pinned_origin_and_execution_copy(
    assignment, tmp_path, standalone
):
    ledger, source_root, source_eid, receipts = assignment
    store = ledger.incarichi()
    source_fields = fields(receipts)
    saved = store.update(source_root, source_eid, source_fields, "")
    declaration = source_fields["results"][0]
    source_revision = saved["revision"]
    if standalone:
        published = ledger.deliverables().publish(
            source_root,
            source_eid,
            "opinion",
            "Parere",
            publish_files(tmp_path),
            0,
            "issue-1",
        )["issued"]
        source_revision = published["content_sha256"]
        declaration = {
            "reference": {"entry_key": "opinion", "revision": 1, "format": "md"},
            "label": "Parere",
            "sha256": published["formats"][0]["sha256"],
        }
    destination = tmp_path / "New project"
    destination.mkdir()
    cid = "client_" + "9" * 24
    ledger.create_client_manifest(destination, cid)
    eid = ledger.create_engagement(destination, cid, "Business plan")["engagement_id"]
    origin = {
        "client_id": CLIENT,
        "engagement_id": source_eid,
        "revision": source_revision,
        **declaration,
    }
    before = preserved(source_root)
    reused = store.reuse(destination, eid, source_root, origin, "source")
    again = store.reuse(destination, eid, source_root, origin, "source")
    assert reused["receipt"]["input_id"] == again["receipt"]["input_id"]
    assert reused["receipt"]["origin"] == origin
    assert preserved(source_root) == before
    assert store.overview(destination, eid)["documents"][0]["origin"] == origin
    run = ledger.prepare_run(
        destination,
        cid,
        eid,
        "business-planning",
        "1.0.0",
        input_ids=[reused["receipt"]["input_id"]],
        label="Plan",
        purpose="Synthetic provenance test",
    )
    ledger.start_run(destination, eid, run["run"]["run_id"])
    context = load_client_engagement_context_file(
        Path(run["context_path"]), expected_workflow_id="business-planning"
    )
    assert context["input_bindings"][0]["origin"] == origin
    execution = Path(context["input_bindings"][0]["path"])
    digest = hashlib.sha256(execution.read_bytes()).hexdigest()
    # A later source revision does not implicitly update the receiving job.
    store.update(
        source_root,
        source_eid,
        {**source_fields, "results": [], "continuation": "New work underway"},
        saved["revision"],
    )
    assert (
        store.reuse(destination, eid, source_root, origin, "source")["receipt"][
            "input_id"
        ]
        == reused["receipt"]["input_id"]
    )
    selected = Path(
        store.document(source_root, source_eid, origin["reference"])["path"]
    )
    selected.unlink()
    reloaded = load_client_engagement_context_file(
        Path(run["context_path"]), expected_workflow_id="business-planning"
    )
    assert reloaded["input_bindings"][0]["origin"] == origin
    assert (
        hashlib.sha256(execution.read_bytes()).hexdigest() == digest == origin["sha256"]
    )
    with pytest.raises(ledger.LedgerError):
        store.reuse(destination, eid, source_root, origin, "support")


def test_reuse_rejects_undeclared_or_forged_source(assignment, tmp_path):
    ledger, root, eid, receipts = assignment
    store = ledger.incarichi()
    saved = store.update(root, eid, fields(receipts), "")
    dest = ledger.create_engagement(root, CLIENT, "Plan")["engagement_id"]
    origin = {
        "client_id": CLIENT,
        "engagement_id": eid,
        "revision": saved["revision"],
        **fields(receipts)["results"][0],
    }
    for changed in (
        {"sha256": "f" * 64},
        {"label": "Wrong result"},
        {"reference": {"input_id": receipts[0]["input_id"]}},
        {"client_id": "client_" + "9" * 24},
    ):
        with pytest.raises(ledger.LedgerError):
            store.reuse(root, dest, root, {**origin, **changed}, "source")
    assert ledger.list_inputs(root, dest) == ()


def test_codex_chat_identity_generates_canonical_link_and_rejects_mismatch(assignment):
    ledger, root, eid, receipts = assignment
    entry = {
        "host": "codex",
        "thread_id": "01a1d9b7-85be-7e51-892b-daef5a9a53b7",
        "title": "Actual chat",
        "url": "",
    }
    data = {**fields(receipts), "conversations": [entry]}
    saved = ledger.incarichi().update(root, eid, data, "")
    assert (
        ledger.incarichi().overview(root, eid)["conversations"][0]["url"]
        == "codex://threads/" + entry["thread_id"]
    )
    for value in (
        "codex://threads/new",
        "https://chatgpt.com/c/different",
        "javascript:alert(1)",
    ):
        with pytest.raises(ledger.LedgerError):
            ledger.incarichi().update(
                root,
                eid,
                {**data, "conversations": [{**entry, "url": value}]},
                saved["revision"],
            )


@pytest.mark.parametrize(
    "workflow", sorted(set(VERA_CLIENT_WORKFLOW_IDS) | set(PUBLIC_PIPELINES))
)
def test_shared_binding_and_versioned_publication_for_every_archive_pipeline(
    assignment, tmp_path, workflow
):
    ledger, root, eid, _ = assignment
    begin = ledger.incarichi().begin(root, eid, workflow, "Requested professional work")
    assert begin["workflow_id"] == workflow
    assert Path(begin["working_directory"]).is_dir()
    # Draft files in the working area do not appear as issued deliverables.
    draft = Path(begin["working_directory"]) / "Draft.txt"
    draft.write_text("Work in progress")
    assert ledger.incarichi().overview(root, eid)["deliverables"] == []
    issued = ledger.deliverables().publish(
        root,
        eid,
        "main-result",
        "Requested result",
        publish_files(tmp_path),
        0,
        "issue-1",
    )
    overview = ledger.incarichi().overview(root, eid)
    assert (
        overview["deliverables"][0]["current_revision"]
        == issued["current_revision"]
        == 1
    )
    assert len(overview["deliverables"][0]["versions"][0]["formats"]) == 2
    assert (
        ledger.incarichi().begin(root, eid, workflow, "Retry")["revision"]
        == begin["revision"]
    )


def test_concurrent_publications_cannot_overwrite_each_other(assignment, tmp_path):
    ledger, root, eid, _ = assignment
    ledger.incarichi().begin(root, eid, "business-planning", "Plan")
    files = publish_files(tmp_path)

    def save(key):
        try:
            return ledger.deliverables().publish(
                root, eid, "plan", "Plan", files, 0, key
            )["saved"]
        except ledger.LedgerError as exc:
            assert "another chat" in str(exc)
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(save, ("first", "second")))
    assert sorted(outcomes) == [False, True]
    assert ledger.deliverables().entry(root, eid, "plan")["current_revision"] == 1


def test_changed_or_duplicate_format_cannot_publish_and_partial_draft_stays_out(
    assignment, tmp_path
):
    ledger, root, eid, _ = assignment
    ledger.incarichi().begin(root, eid, "business-planning", "Plan")
    files = publish_files(tmp_path)
    for selected in (
        [files[0], files[0]],
        [{**files[0], "sha256": "f" * 64}],
        [{**files[0], "source_path": "relative.md"}],
    ):
        with pytest.raises(ledger.LedgerError):
            ledger.deliverables().publish(
                root, eid, "plan", "Plan", selected, 0, "first"
            )
    assert ledger.incarichi().overview(root, eid)["deliverables"] == []


def test_missing_historical_file_does_not_hide_or_block_new_revision(
    assignment, tmp_path
):
    ledger, root, eid, _ = assignment
    ledger.incarichi().begin(root, eid, "business-planning", "Plan")
    ledger.deliverables().publish(
        root, eid, "plan", "Plan", publish_files(tmp_path), 0, "first"
    )
    document = ledger.incarichi().document(
        root, eid, {"entry_key": "plan", "revision": 1, "format": "md"}
    )
    Path(document["path"]).unlink()
    ledger.deliverables().publish(
        root, eid, "plan", "Plan", publish_files(tmp_path, "New"), 1, "second"
    )
    entry = ledger.incarichi().overview(root, eid)["deliverables"][0]
    assert entry["current_revision"] == 2
    assert entry["versions"][0]["formats"][0]["available"] is False
    assert all(item["available"] for item in entry["versions"][1]["formats"])


def test_explicit_legacy_output_adoption_keeps_receipts_and_source_documents(
    assignment,
):
    ledger, root, eid, receipts = assignment
    ledger.incarichi().begin(root, eid, "quesito-legale-fiscale", "Opinion")
    before = preserved(root)
    receipt = receipts[-1]
    selected = {
        "format": "md",
        "source_path": receipt["path"],
        "sha256": receipt["sha256"],
        "legacy_input_id": receipt["input_id"],
    }
    ledger.deliverables().publish(
        root, eid, "opinion", "Parere", [selected], 0, "adopt-opinion"
    )
    overview = ledger.incarichi().overview(root, eid)
    assert len(overview["documents"]) == 2
    assert len(overview["deliverables"]) == 1
    assert overview["legacy_output_inputs"] == [receipt["input_id"]]
    assert {name: preserved(root)[name] for name in before} == before
    assert len(ledger.list_inputs(root, eid)) == 3
    # Same bytes with a different claimed receipt cannot reclassify a source.
    with pytest.raises(ledger.LedgerError, match="differs"):
        ledger.deliverables().publish(
            root,
            eid,
            "opinion",
            "Parere",
            [{**selected, "legacy_input_id": receipts[0]["input_id"]}],
            1,
            "forged-adoption",
        )


def test_mixed_legacy_jobs_map_explicitly_without_rewriting_any_old_file(assignment):
    ledger, root, source_eid, receipts = assignment
    store = ledger.incarichi()
    targets = []
    for workflow, label in (
        ("treasury-forecast", "Treasury"),
        ("business-planning", "Plan"),
    ):
        run = ledger.prepare_run(
            root,
            CLIENT,
            source_eid,
            workflow,
            "1.0.0",
            input_ids=[receipts[0]["input_id"]],
            label=label,
            purpose=label,
        )
        eid = ledger.create_engagement(root, CLIENT, label)["engagement_id"]
        store.begin(root, eid, workflow, label)
        targets.append({"engagement_id": eid, "run_ids": [run["run"]["run_id"]]})
    original = preserved(root)
    with pytest.raises(ledger.LedgerError, match="every historical run"):
        store.map_legacy(root, source_eid, targets[:1])
    with pytest.raises(ledger.LedgerError, match="different purpose"):
        store.map_legacy(
            root,
            source_eid,
            [
                {**targets[0], "run_ids": targets[1]["run_ids"]},
                {**targets[1], "run_ids": targets[0]["run_ids"]},
            ],
        )
    mapped = store.map_legacy(root, source_eid, targets)
    assert store.map_legacy(root, source_eid, list(reversed(targets))) == mapped
    assert {name: preserved(root)[name] for name in original} == original
    assert len(store.overview(root, source_eid)["legacy_assignments"]) == 2
    for target in targets:
        history = store.overview(root, target["engagement_id"])[
            "historical_assignments"
        ]
        assert history[0]["engagement_id"] == source_eid
        assert history[0]["runs"][0]["run_id"] == target["run_ids"][0]
    with pytest.raises(ledger.LedgerError, match="mapped incarichi"):
        store.begin(
            root, source_eid, "treasury-forecast", "Accidental continued mixed work"
        )
    assert store.read(root, source_eid)["revision"] == ""


def test_desktop_metadata_does_not_hide_issued_results(assignment, tmp_path):
    ledger, root, eid, _ = assignment
    ledger.incarichi().begin(root, eid, "business-planning", "Plan")
    ledger.deliverables().publish(
        root, eid, "plan", "Plan", publish_files(tmp_path), 0, "issue"
    )
    directory = root / "Vera/engagements" / eid / "deliverables"
    for folder in (directory, directory / "plan"):
        for name in (".DS_Store", "Thumbs.db", "desktop.ini"):
            (folder / name).write_text("desktop metadata")
    view = ledger.incarichi().overview(root, eid)
    assert view["deliverables"][0]["current_revision"] == 1
    assert view["deliverable_issues"] == []

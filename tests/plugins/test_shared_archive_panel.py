"""The shared panel preserves product ownership and verified saved references."""

from __future__ import annotations

from functools import partial
from types import SimpleNamespace

import pytest

from tests.plugins.test_vera_customer_folder_ledger import (
    archive_core,
    archive_script_imports,
    client_case,
)

__all__: list[str] = []


@pytest.fixture
def panel_case(tmp_path, monkeypatch, archive_core):
    monkeypatch.delenv("LUCIA_ASSURANCE_HOST", raising=False)
    monkeypatch.delenv("CLARA_ARCHIVE_HOST", raising=False)
    case = client_case.__wrapped__(tmp_path, archive_core)
    names = (
        "list_studio_clients",
        "get_studio_client_folder",
        "get_studio_incarico",
        "read_studio_incarico_document",
        "studio_archive_status",
        "refresh_archive",
        "search_archive",
        "open_archive_source",
    )
    core = SimpleNamespace(
        ledger=archive_core.ledger,
        **{
            name: partial(getattr(archive_core, name), state_dir=case.state_dir)
            for name in names
        },
    )
    return core, case


def test_shared_adapter_directory_and_exact_saved_document(
    panel_case, archive_core, tmp_path
):
    from archive_panel import dispatch

    core, case = panel_case
    source = tmp_path / "source.txt"
    source.write_text("Synthetic saved opinion")
    archive_core.import_studio_client_document(
        case.client_id,
        source,
        "source",
        engagement_id=case.engagement_id,
        state_dir=case.state_dir,
    )
    root = dispatch(core, "catalogue", {})
    assert [row["client_id"] for row in root["clients"]] == [case.client_id]
    scope = {"client_id": case.client_id}
    assert (
        dispatch(core, "catalogue", scope)["engagements"][0]["engagement_id"]
        == case.engagement_id
    )
    scope["engagement_id"] = case.engagement_id
    saved = dispatch(core, "catalogue", scope)["incarico"]
    opened = dispatch(
        core,
        "document",
        {
            **scope,
            "reference": next(
                item for item in saved["documents"] if item["name"] == "source.txt"
            )["reference"],
        },
    )
    assert opened["preview"] == source.read_text()
    assert set(opened) == {"name", "path", "preview"}
    assert dispatch(core, "matter", {**scope, "offset": 30})["documents"] == []
    assert source.read_text() == "Synthetic saved opinion"
    with pytest.raises(ValueError, match="Unknown Archive"):
        dispatch(core, "unknown", scope)


def test_shared_adapter_scoped_search_verifies_selected_result(panel_case):
    from archive_panel import dispatch

    core, case = panel_case
    (case.client_root / "opinion.txt").write_text("panelneedle opinion")
    query = {"client_id": case.client_id, "query": "panelneedle"}
    result = dispatch(core, "search", query)
    assert result["results"][0]["title"] == "opinion.txt"
    opened = dispatch(
        core, "source", {**query, "source_id": result["results"][0]["source_id"]}
    )
    assert opened["source_verified"] is True
    with pytest.raises(PermissionError, match="scoped search"):
        dispatch(core, "source", {**query, "source_id": "foreign"})
    with pytest.raises(ValueError, match="explicitly"):
        dispatch(core, "search", {"query": "panelneedle"})
    with pytest.raises(PermissionError, match="registered"):
        dispatch(core, "search", {"client_id": "foreign", "query": "panelneedle"})
    assert dispatch(core, "search", {"all_clients": True, "query": "panelneedle"})[
        "results"
    ]


def test_shared_adapter_rejects_foreign_project_before_read(panel_case, monkeypatch):
    from archive_panel import dispatch, page

    core, case = panel_case
    monkeypatch.setenv("LUCIA_ASSURANCE_HOST", "1")
    assert dispatch(core, "catalogue", {})["clients"] == []
    with pytest.raises(PermissionError, match="product Archive"):
        dispatch(
            core,
            "document",
            {
                "client_id": case.client_id,
                "engagement_id": case.engagement_id,
                "reference": {"input_id": "foreign"},
            },
        )
    for args in (
        {"engagement_id": case.engagement_id},
        {"offset": -1},
        {"offset": True},
    ):
        with pytest.raises(ValueError):
            dispatch(core, "catalogue", args)
    for operation, args in (("matter", {}), ("setup", {"confirmed": False})):
        with pytest.raises(ValueError):
            dispatch(core, operation, args)
    assert page([{}] * 31, {})["has_more"] is True
    assert (
        dispatch(
            SimpleNamespace(
                setup_archive_with_folder_picker=lambda: {"setup_status": "cancelled"}
            ),
            "setup",
            {"confirmed": True},
        )["setup_status"]
        == "cancelled"
    )
    with pytest.raises(ValueError, match="non è collegata"):
        dispatch(
            SimpleNamespace(list_studio_clients=lambda: {"configured": False}),
            "search",
            {"query": "needle", "all_clients": True},
        )

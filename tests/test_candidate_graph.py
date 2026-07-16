from __future__ import annotations

from pathlib import Path
import importlib
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _ensure_package(name: str, path: Path) -> None:
    if name in sys.modules:
        return
    pkg = types.ModuleType(name)
    pkg.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[name] = pkg


_ensure_package("src", SRC)
_ensure_package("src.check_statements", SRC / "check_statements")

candidate_graph = importlib.import_module("src.check_statements.candidate_graph")


def test_candidate_graph_store_and_retrieve_edge() -> None:
    graph = candidate_graph.CandidateGraph(bank_size=2)
    edge = candidate_graph.CandidateEdge(
        bank_index=1,
        ledger_index=7,
        amount_delta=0.25,
        date_diff_days=3,
    )

    graph.add_edge(edge)

    assert graph.edges_for_bank(1) == [edge]
    assert graph.edges_for_bank(0) == []


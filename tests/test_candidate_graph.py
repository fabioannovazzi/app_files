from __future__ import annotations

from src.check_statements import candidate_graph


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

from __future__ import annotations

from itertools import combinations
from typing import Iterable, Sequence

import polars as pl

from src.hierarchy_logic import resolve_hierarchies as _resolve
from modules.utilities.utils import get_schema_and_column_names

__all__ = [
    "resolve_hierarchies",
    "detect_hierarchies",
    "order_hierarchy_pairs",
    "get_ambiguous_rows",
]


def _is_parent_child(
    df: pl.DataFrame | pl.LazyFrame,
    child_col: str,
    parent_col: str,
    ambiguous_pct: int,
    *,
    allow_parent_more_uniques: bool = True,
) -> bool:
    """Return ``True`` if most children map uniquely to a parent.

    The function accepts either a :class:`polars.DataFrame` or
    :class:`polars.LazyFrame`.

    Parameters
    ----------
    allow_parent_more_uniques:
        When ``False`` the parent column may not have more unique values than
        the child column. Defaults to ``True``.
    """

    frame = df.collect() if isinstance(df, pl.LazyFrame) else df

    child_unique = frame.select(pl.col(child_col).n_unique()).item()
    parent_unique = frame.select(pl.col(parent_col).n_unique()).item()
    if child_unique == 0 or (
        not allow_parent_more_uniques and parent_unique > child_unique
    ):
        return False

    mapping = frame.group_by(child_col).agg(pl.col(parent_col).n_unique().alias("n"))
    ambiguous = mapping.filter(pl.col("n") > 1).select(pl.len()).item()
    pct = ambiguous / child_unique * 100
    return pct <= ambiguous_pct


def _ambiguous_children(
    df: pl.DataFrame | pl.LazyFrame,
    child_col: str,
    parent_col: str,
    ambiguous_pct: int,
) -> set[str]:
    """Return children whose conflicting parents exceed ``ambiguous_pct``."""

    if ambiguous_pct >= 100:
        return set()

    frame = df.collect() if isinstance(df, pl.LazyFrame) else df

    stats = (
        frame.group_by([child_col, parent_col])
        .len()
        .group_by(child_col)
        .agg(pl.col("len").max().alias("_max"), pl.col("len").sum().alias("_tot"))
        .with_columns(
            ((pl.col("_tot") - pl.col("_max")) / pl.col("_tot") * 100).alias("pct")
        )
    )
    return set(
        stats.filter(pl.col("pct") > ambiguous_pct).get_column(child_col).to_list()
    )


def _build_chains(pairs: Iterable[tuple[str, str]]) -> list[list[str]]:
    """Return all root → leaf chains described by ``pairs``.

    Duplicate ``(child, parent)`` mappings are preserved so that every parent
    relationship is represented in the resulting chains.
    """

    from collections import defaultdict

    parents_by_child: defaultdict[str, list[str]] = defaultdict(list)
    for child, parent in pairs:
        parents_by_child[child].append(parent)

    children = set(parents_by_child)
    parents = {p for vals in parents_by_child.values() for p in vals}
    leaves = sorted(children - parents)

    chains: list[list[str]] = []

    def dfs(node: str, path: list[str]) -> None:
        if node not in parents_by_child:
            chains.append(list(reversed(path)))
            return
        advanced = False
        for parent in parents_by_child[node]:
            if parent in path:
                continue
            advanced = True
            dfs(parent, path + [parent])
        if not advanced:
            chains.append(list(reversed(path)))

    for leaf in leaves:
        dfs(leaf, [leaf])

    return chains


def order_hierarchy_pairs(pairs: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """Return unique ``(child, parent)`` pairs ordered leaf → root."""

    uniq_pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for pair in pairs:
        if pair not in seen:
            uniq_pairs.append(pair)
            seen.add(pair)

    if not uniq_pairs:
        return []

    from collections import defaultdict

    graph: defaultdict[str, list[str]] = defaultdict(list)
    indegree: dict[str, int] = {}
    for child, parent in uniq_pairs:
        graph[child].append(parent)
        indegree[parent] = indegree.get(parent, 0) + 1
        indegree.setdefault(child, 0)

    children = set(graph)
    parents = {p for vals in graph.values() for p in vals}
    queue = [n for n in sorted(children - parents)]
    topo: list[str] = []
    while queue:
        node = queue.pop(0)
        topo.append(node)
        for parent in graph.get(node, []):
            indegree[parent] -= 1
            if indegree[parent] == 0:
                queue.append(parent)

    remaining = [n for n in indegree if n not in topo]
    topo.extend(sorted(remaining))

    order_map = {n: i for i, n in enumerate(topo)}
    return sorted(uniq_pairs, key=lambda p: (order_map[p[0]], order_map[p[1]]))


def resolve_hierarchies(
    df: pl.DataFrame | pl.LazyFrame,
    pairs: Sequence[tuple[str, str]],
    weight_col: str | None,
    ambiguous_pct: int,
    param_dict: dict,
    ambiguous_placeholder: str | None = None,
) -> tuple[pl.DataFrame, dict]:
    """Apply hierarchy resolution for multiple child/parent pairs.

    Parameters
    ----------
    df:
        Source dataset as either a :class:`polars.DataFrame` or
        :class:`polars.LazyFrame`.
    pairs:
        Pairs of ``(child_column, parent_column)`` describing the hierarchies
        to resolve. Ordering is determined automatically so that leaf columns
        are processed before their parents.
    weight_col:
        Optional weighting column used when selecting the most likely parent.
    ambiguous_pct:
        Allowed percentage of ambiguous child mappings to keep.
    param_dict:
        Parameter dictionary passed through unchanged.
    ambiguous_placeholder:
        Value used for the parent column when a child is deemed too
        ambiguous. If ``None`` the original parent value is retained.
    """

    if isinstance(df, pl.LazyFrame):
        df = df.collect()

    result = df.with_row_index("_idx")
    for child_col, parent_col in order_hierarchy_pairs(pairs):
        ambiguous = _ambiguous_children(result, child_col, parent_col, ambiguous_pct)
        subset = result.filter(~pl.col(child_col).is_in(ambiguous))
        mapped = (
            _resolve(subset, child_col, [parent_col], weight_col=weight_col)
            .select("_idx", parent_col)
            .collect()
        )
        result = (
            result.join(mapped, on="_idx", how="left", suffix="_new")
            .with_columns(
                pl.col(f"{parent_col}_new")
                .fill_null(pl.col(parent_col))
                .alias(parent_col)
            )
            .drop(f"{parent_col}_new")
        )
        if ambiguous_placeholder is not None:
            if ambiguous:
                result = result.with_columns(
                    pl.when(pl.col(child_col).is_in(list(ambiguous)))
                    .then(pl.lit(ambiguous_placeholder))
                    .otherwise(pl.col(parent_col))
                    .alias(parent_col)
                )
            result = result.with_columns(
                pl.col(parent_col)
                .fill_null(ambiguous_placeholder)
                .replace("", ambiguous_placeholder)
                .alias(parent_col)
            )

    return result.drop("_idx"), param_dict


def detect_hierarchies(
    df: pl.DataFrame | pl.LazyFrame,
    ambiguous_pct: int,
    *,
    expand: bool = False,
    allow_parent_more_uniques: bool = True,
) -> pl.DataFrame | list[list[str]]:
    """Identify likely child → parent column mappings.

    Parameters
    ----------
    df:
        Input dataset as a :class:`polars.DataFrame` or
        :class:`polars.LazyFrame`.
    ambiguous_pct:
        Allowed percentage of ambiguous children before a mapping is rejected.
    expand:
        If ``True`` return full hierarchy chains instead of pairs.
    allow_parent_more_uniques:
        If ``False`` a parent column with more distinct values than the child
        column is rejected early. Defaults to ``True``.
    """

    frame = df.collect() if isinstance(df, pl.LazyFrame) else df

    utf8_cols, _ = get_schema_and_column_names(frame.select(pl.col(pl.Utf8)))
    if utf8_cols:
        uniq_df = frame.select([pl.col(c).n_unique().alias(c) for c in utf8_cols])
        columns, _ = get_schema_and_column_names(uniq_df)
        uniq_counts = dict(zip(columns, uniq_df.row(0)))
    else:
        uniq_counts = {}
    string_cols = [c for c in utf8_cols if uniq_counts.get(c, 0) > 1]
    if len(string_cols) < 2:
        return pl.DataFrame(
            {
                "child": pl.Series([], dtype=pl.Utf8),
                "parent": pl.Series([], dtype=pl.Utf8),
            }
        )

    candidate: list[tuple[str, str]] = []
    for c1, c2 in combinations(string_cols, 2):
        if _is_parent_child(
            frame,
            c1,
            c2,
            ambiguous_pct,
            allow_parent_more_uniques=allow_parent_more_uniques,
        ):
            candidate.append((c1, c2))
        if _is_parent_child(
            frame,
            c2,
            c1,
            ambiguous_pct,
            allow_parent_more_uniques=allow_parent_more_uniques,
        ):
            candidate.append((c2, c1))

    if not candidate:
        return pl.DataFrame(
            {
                "child": pl.Series([], dtype=pl.Utf8),
                "parent": pl.Series([], dtype=pl.Utf8),
            }
        )

    if expand:
        return _build_chains(candidate)

    return pl.DataFrame(candidate, schema=["child", "parent"], orient="row")


def get_ambiguous_rows(
    df: pl.DataFrame | pl.LazyFrame,
    pairs: Sequence[tuple[str, str]],
    ambiguous_pct: int,
) -> pl.DataFrame:
    """Return rows whose children map to multiple parents."""

    frame = df.collect() if isinstance(df, pl.LazyFrame) else df
    with_idx = frame.with_row_index("_idx")
    indices: set[int] = set()
    for child_col, parent_col in pairs:
        amb_children = _ambiguous_children(frame, child_col, parent_col, ambiguous_pct)
        if amb_children:
            ids = (
                with_idx.filter(pl.col(child_col).is_in(amb_children))
                .get_column("_idx")
                .to_list()
            )
            indices.update(ids)

    return with_idx.filter(pl.col("_idx").is_in(sorted(indices))).drop("_idx")

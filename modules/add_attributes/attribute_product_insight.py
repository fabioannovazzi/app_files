from __future__ import annotations

from typing import Any, Iterable, Sequence

import polars as pl
from scipy import stats
from sklearn.tree import DecisionTreeClassifier
from src.io_utils import get_schema_and_column_names

__all__ = ["group_stats_and_tests", "train_decision_tree"]


def group_stats_and_tests(
    df: pl.DataFrame,
    attribute_col: str,
    metrics: Sequence[str],
    *,
    top_flag_col: str | None = None,
) -> dict[str, Any]:
    """Return summary statistics and tests for attribute groups.

    Parameters
    ----------
    df:
        Input data containing at least ``attribute_col`` and columns listed in
        ``metrics``. Optionally includes ``top_flag_col`` for the chi-square
        test.
    attribute_col:
        Column with attribute values.
    metrics:
        Metrics to analyse (e.g. ``["Sales", "Units", "Price"]``).
    top_flag_col:
        Optional boolean or integer column marking top products. When provided
        a chi-square test of independence is computed.
    """
    cols, _ = get_schema_and_column_names(df)

    groups = df.group_by(attribute_col).agg(
        [pl.len().alias("count")]
        + [
            pl.col(m).mean().alias(f"mean_{m.lower()}")
            for m in metrics
            if m in cols
        ]
    )

    anova: dict[str, dict[str, float]] = {}
    group_vals = df[attribute_col].unique().to_list()
    for metric in metrics:
        if metric not in cols:
            continue
        samples: list[pl.Series] = [
            df.filter(pl.col(attribute_col) == val)[metric] for val in group_vals
        ]
        if len(samples) <= 1:
            continue
        f_stat, p_val = stats.f_oneway(*(s.to_numpy() for s in samples))
        anova[metric] = {"F": float(f_stat), "p": float(p_val)}

    chi2_res: dict[str, Any] | None = None
    if top_flag_col and top_flag_col in cols:
        cont = (
            df.group_by([attribute_col, top_flag_col])
            .agg(pl.len().alias("count"))
            .pivot(top_flag_col, index=attribute_col, values="count")
            .fill_null(0)
        )
        observed = cont.drop(attribute_col).to_numpy()
        chi2, p, dof, expected = stats.chi2_contingency(observed)
        chi2_res = {
            "chi2": float(chi2),
            "p": float(p),
            "dof": int(dof),
            "expected": pl.DataFrame(
                expected,
                schema=get_schema_and_column_names(cont.drop(attribute_col))[1],
            ),
        }

    return {"stats": groups, "anova": anova, "chi2": chi2_res}


def train_decision_tree(
    df: pl.DataFrame,
    features: Sequence[str],
    target: str,
    *,
    max_depth: int | None = None,
    random_state: int | None = 0,
) -> tuple[DecisionTreeClassifier, dict[str, float]]:
    """Fit a decision tree and return it with feature importances.

    Parameters
    ----------
    df:
        Dataset containing ``features`` and ``target``.
    features:
        Predictor column names.
    target:
        Column to predict.

    Returns
    -------
    tuple[DecisionTreeClassifier, dict[str, float]]
        The trained classifier and a mapping of feature name to importance.
    """
    clf = DecisionTreeClassifier(max_depth=max_depth, random_state=random_state)
    clf.fit(df.select(features).to_numpy(), df[target].to_numpy())
    importances = {
        feat: float(imp) for feat, imp in zip(features, clf.feature_importances_)
    }
    return clf, importances

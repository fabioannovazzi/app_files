from . import attribute_taxonomy as attribute_taxonomy_module
from .add_attributes import add_attributes
from .attribute_classification import (
    classify_attributes_for_products,
    classify_product_attributes,
    discover_objective_attributes_for_category,
)
from .attribute_discovery import (
    deduplicate_attributes,
    discover_attributes_for_category,
)
from .attribute_impact_analysis import merge_scores_with_metrics
from .attribute_product_insight import group_stats_and_tests, train_decision_tree
from .attribute_scoring import (
    score_attributes_for_products,
    score_product_attributes,
    score_to_stars,
)
from .column_inference import infer_column_roles
from .grouping import select_grouping_level
from .normalization import normalize_product_key
from .pareto import compute_pareto_ranking, infer_amount_column

attribute_taxonomy = attribute_taxonomy_module

__all__ = [
    "attribute_taxonomy",
    "add_attributes",
    "infer_column_roles",
    "select_grouping_level",
    "infer_amount_column",
    "compute_pareto_ranking",
    "deduplicate_attributes",
    "discover_attributes_for_category",
    "discover_objective_attributes_for_category",
    "classify_product_attributes",
    "classify_attributes_for_products",
    "score_product_attributes",
    "score_attributes_for_products",
    "score_to_stars",
    "merge_scores_with_metrics",
    "group_stats_and_tests",
    "train_decision_tree",
    "normalize_product_key",
]

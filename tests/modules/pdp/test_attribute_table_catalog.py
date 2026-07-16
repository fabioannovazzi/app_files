from __future__ import annotations

from modules.pdp.attribute_table_catalog import load_attribute_table_catalog


def test_attribute_table_catalog_exposes_artifact_contracts() -> None:
    catalog = load_attribute_table_catalog()

    assert catalog.schema_version == "1.0"
    assert catalog.execution_contract["entry_point"] == (
        "modules.pdp.attribute_table_templates.build_attribute_tables_from_package"
    )
    assert catalog.execution_contract["required_parameters"] == ["package_dir"]
    assert set(catalog.capabilities) == {
        "attributes.attribute_bundle_comparison_table",
        "attributes.attribute_bridge_table",
        "attributes.rank_weighted_visibility_table",
        "attributes.product_signal_evidence_table",
    }
    for capability in catalog.capabilities.values():
        assert capability.required_parameters == ("package_dir",)
        assert capability.optional_parameters == ("output_dir", "table_keys")
        assert capability.use_when
        assert capability.avoid_when
        assert capability.table_template
        assert capability.source_files

CLI Index
========

This is a quick map of the `scripts/` CLIs, grouped by purpose. Use `PYTHONPATH=$PWD ./.venv/bin/python scripts/<name>.py --help` where applicable. Paths are relative to the repo root.

Attribute / catalog pipeline
- `export_pdp_attributes.py` — rebuild deterministic and text-LLM PDP attributes into the configured PDP database, and optionally run VLM in the same command via `--run-vlm`. Use `--retailer <name>` and `--category <key>` to limit scope.
- `run_pdp_parser.py` — run the PDP parser to ingest product detail pages.
- `update_attribute_activity.py` — refreshes attribute activity flags.
- `generate_taxonomy_branch.py` — scaffolds a new taxonomy branch.
- `clean_taxonomy.py` — utility to clean taxonomy definitions.
- `brand_web_search_attribute_fill.py` — fill missing PDP taxonomy attributes from brand-site web search, independent of any sales dataset. Use `--retailer <name>` and `--category <key>` to limit scope.
- `pdp_attribute_mapping_vlm.py` — direct image/VLM helper; the normal scoped flow is `export_pdp_attributes.py --run-vlm`.
- `run_retailer_listing_discovery_cdp.py --retailer kiko` — preferred Kiko discovery path; captures listing rows plus Kiko PLP filter facets from embedded Algolia state and writes first-choice Kiko filter evidence; see `docs/kiko_filter_discovery.md`.
- `run_kiko_filter_discovery.py` — lower-level Kiko-only fallback for filter evidence capture when listing discovery is not needed.
- `prejoin_sales.py` — run only dataset-specific sales-join outputs using the shared mapped cache; it serves the sales-analysis/legacy-attribute-analysis pipeline and is not an input to retailer-signals, brand-fit, or product-hypothesis reports.
- `prejoin_sales_join.py` — compatibility alias for the same sales-join-only workflow.

Report package generation
- `build_retailer_category_evidence_pack.py --retailer <retailer>` — rebuild every discovered category package for one retailer from the configured PDP database listing/filter observations and PDP attributes. Use `--categories <category> [<category> ...]` to rebuild only selected categories; see `docs/retailer_category_evidence_pack.md` for top-seller and sale-pressure cohort definitions.
- `build_brand_retailer_reference_package.py` — build Brand Fit packages from an existing retailer-signal package plus brand catalog data. The matching retailer-signal brief is required; see `docs/brand_fit_packages.md`.
CDP / PDP collection utilities
- `cdp_collect_links.py` — collect product links.
- `cdp_fetch_pdp.py` — fetch PDP content.
- `cdp_probe.py` — probe CDP endpoints (diagnostic).
- Chewy listing discovery has retailer-specific KPSDK behavior; see `docs/chewy_listing_discovery.md`.

Maintenance / utilities
- `inspect_parsed_transactions.py` — inspect parsed transaction data (diagnostic).
- `instrument_loader.py` — instrumentation helper.
- `cleanup_sessions.py` — clean up session artifacts.
- `build_png_examples_gallery.py` — rebuild a chart PNG gallery from a source artifact tree; see `docs/png_examples_gallery.md`.
- `build_static_png_gallery_inventory.py` — build a local `static/shared/png-gallery` inventory from generated chart artifacts and copied sidecars.
- `validate_png_gallery_manifest.py` — validate gallery manifests, including strict artifact-readiness checks with `--require-artifact-ready`.
- `audit_png_example_artifacts.py` — summarize renderer labels, source PNG residue, and HTML-only chart artifacts for the PNG examples workspace.
- `build_chart_selection_family_playbooks.py` — build per-family chart selector playbooks from the selection manifest for human review of chart-choice cues, roles, competitors, and examples.
- `build_chart_selection_family_review.py` — build the family-by-family chart selector review that answers specificity, competitor, focus-token, role, and PNG-purpose questions.
- `audit_chart_plugin_parameter_contract.py` — audit whether chart-selection manifest roles map to concrete plugin recipe, catalog, or artifact-contract parameters.
- `audit_chart_selection_examples.py` — audit whether manifest positive, negative, and ambiguous chart-selection examples are usable selector evidence.
- `audit_chart_selection_pairwise_ambiguity.py` — audit whether mechanically similar chart capabilities expose explicit selector tie-breakers and pairwise example evidence.
- `prepare_reporting_visual_review.py` — prepare a one-chart or all-gallery visual review packet with exact artifact paths, sidecars, inferred visual family, and fixed reporting references; see `docs/plugin_reporting_visual_editing.md`.
- `validate_reporting_visual_references.py` — validate the classified reporting reference corpus and local cached image assets used by reporting visual review.

Unknown/less documented
- If a script here is still unclear, run it with `--help` or inspect its top-level docstring/source for arguments and side effects.

Notes
- Most scripts expect `PYTHONPATH=$PWD` and the project interpreter `./.venv/bin/python`.
- For attribute pipeline scripts, ensure PDP database connectivity and secrets are configured.

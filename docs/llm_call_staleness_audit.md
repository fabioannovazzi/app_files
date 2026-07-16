# LLM Call Staleness Audit

Last audited: 2026-06-08

This audit separates stale LLM paths from live calls that should not be removed.
It uses the current production query steps in `modules.utilities.config`, direct
model-call scans, and production call-site references.

## Protected Attribute/PDP Calls

Do not flag these for deletion. They are part of the active attribute-analysis,
PDP, taxonomy, or product-evidence pipelines.

| Query step | Primary production callers | Keep rationale |
| --- | --- | --- |
| `attributeClassificationQuery` | `modules/add_attributes/add_attributes.py`, `modules/add_attributes/attribute_classification.py`, `modules/add_attributes/pdp_attribute_export.py` | Core attribute classification and PDP export pipeline. |
| `attributeDiscoveryQuery` | `modules/add_attributes/attribute_discovery.py` | Discovers missing/derived attributes. |
| `attributeScoringQuery` | `modules/add_attributes/attribute_scoring.py` | Scores candidate attribute values. |
| `inferColumnQuery` | `modules/add_attributes/column_inference.py`, `modules/add_attributes/pareto.py`, `modules/llm/random_entries_queries.py` | Used for attribute column inference and journal/check entry column mapping. |
| `categoryWebsiteLookup` | `src/category_lookup.py` | Resolves category websites with market context for attribute discovery. |
| `merchantBrandWebsiteLookup` | `src/merchant_brand_lookup.py` | Resolves merchant/brand websites for attribute/PDP enrichment. |
| `pdpClassificationQuery` | `modules/add_attributes/pdp_attribute_export.py` | PDP attribute classification stage. |
| `pdpVisionAttributeQuery` | `modules/pdp/attribute_mapping_core.py` | PDP image/vision attribute mapping. |
| `pdpWebAttributeQuery` | `modules/pdp/attribute_mapping_core.py` | PDP web-text attribute mapping. |
| `pdpReviewThemeDiscoveryQuery` | `modules/pdp/review_theme_codebook.py` | Review-theme discovery for PDP evidence. |
| `pdpReviewThemeTagQuery` | `modules/pdp/review_theme_codebook.py` | Review-theme tagging for PDP evidence. |
| `synonymResolutionQuery` | `modules/add_attributes/synonym_enrichment.py` | Taxonomy synonym enrichment. |
| `taxonomyGenerationQuery` | `modules/add_attributes/attribute_classification.py`, `modules/add_attributes/grounding.py`, `modules/add_attributes/synonym_enrichment.py`, `scripts/generate_taxonomy_branch.py` | Taxonomy generation/repair path. |
| `taxonomyGroundingQuery` | `modules/add_attributes/grounding.py`, `modules/add_attributes/synonym_enrichment.py` | Web-grounded taxonomy branch validation/enrichment. |
| `reasonedJudgementQuery` | `scripts/validate_category_analysis.py` | Category/innovation analysis validation; keep with the attribute-analysis reporting scripts. |

## Other Live Calls To Keep

These are not attribute-analysis calls, but current evidence shows they support
active plugin, slide, audit, or utility workflows rather than old GPT-PPT/report
generation.

| Query step | Primary production callers | Keep rationale |
| --- | --- | --- |
| `checkEntriesQuery` | `modules/check_entries/logic.py`, `modules/check_entries/backend.py` | Check Entries plugin workflow. |
| `quickRewriteQuery` | `modules/check_entries/audit_note.py` | Check Entries audit-note rewrite. |
| `llmFallbackQuery` | `modules/llm/model_router.py`, `modules/llm/openai_batch.py`, `modules/conversation/chat_service.py` | Generic OpenAI fallback used by live wrappers. |
| `deepResearchRun` | `src/deep_research_runner.py` | Deep Research runner. |
| `readImageTableQuery` | `src/slides/ocr_service.py` | Slide OCR/table extraction. |
| `readImageTableStructureQuery` | `src/slides/ocr_service.py` | Slide OCR table-structure extraction. |
| `launchValidationReviewQuery` | `src/slides/launch_pdf_validator.py` | Launch report validator; leave launch reports alone. |
| `slideLayoutSemanticCorrectionQuery` | `src/slides/layout_service.py` | Slide layout semantic correction. |
| `slideOcrSemanticQuery` | `src/slides/ocr_service.py` | Slide OCR semantic correction. |
| `slideOcrResidualAuditQuery` | `src/slides/ocr_service.py` | Slide OCR residual audit. |
| `slideOcrVisualCorrectionQuery` | `src/slides/ocr_service.py` | Slide OCR visual correction. |
| `slidesChartTypeQuery` | `src/slides/chart_type_classifier.py` | Slide chart-type classification. |
| `slidesPptxRepairQuery` | `src/slides/pptx_post_render.py` | PPTX post-render repair. |
| `reviewBriefChartInterpretationQuery` | `src/review_brief/generator.py` | Review brief generator; not the old GPT-PPT JSON loop. |
| `reviewBriefNarrativeQuery` | `src/review_brief/generator.py` | Review brief narrative generation; not the old GPT-PPT JSON loop. |

Hosted interviews use direct OpenAI Realtime HTTP calls in
`modules/hosted_interviews/api.py`, shared through `modules/openai_realtime.py`.
That path is intentionally outside the generic LLM wrapper and is not stale.

## Stale Candidates

These are the remaining LLM paths that look stale and are not part of the
attribute-analysis/PDP pipeline.

| Candidate | Query steps / files | Evidence | Likely cleanup scope |
| --- | --- | --- | --- |
| Statement package LLM fallback stubs | `src/statements/llm.py`, `src/statements/llm_page_classifier.py`, `src/statements/strategies.py::strategy_llm_blocks`, statement LLM tests | `extract_transactions_llm` is a TODO that returns `[]` even when `LLM_API_KEY` exists. `LLMPageClassifier` gates on `BANK_PARSE_LLM` and calls `query_llm_return_json` with the old two-argument signature, so it cannot use the current wrapper correctly. This package is separate from the live check-statement/reconciliation plugin paths. | Remove the TODO LLM fallback and optional LLM page classifier, or rewrite them later as a proper wrapper-backed statement parser if that becomes a product goal. |
| LLM refactor helper scripts | `tools/run_codex_llm_wrapper_refactor.py`, `tools/run_codex_llm_naming_params_refactor.py` | Developer automation for historical wrapper migration, not runtime LLM product behavior. | Optional cleanup only; not required for product LLM call removal. |

## Removed Report-Chat Provider Paths

The old report-chat workflow was removed on 2026-06-08. That workflow uploaded
legacy executive-summary JSON and chart PNG bundles, asked follow-up questions
against the report, and post-processed the answer through separate translation
and bolding LLM calls. Removed pieces include:

- `modules/conversation/*`
- the retired report-chat page template
- the report-chat routes in `modules/pdp/api.py`
- the report-chat language/nav copy in `modules/pdp/language.py`
- the conversation-specific LLM router and batch wrapper paths
- the report-chat query-step config entries

## Removed Check-Statements Provider Paths

`checkPatternsQuery`, `descriptionNormaliserQuery`, and `ocrFallbackQuery` were removed from
`modules.utilities.config` on 2026-06-08. The associated provider-backed helper
modules were deleted:

- `src/check_statements/alias_llm.py`
- `src/check_statements/alias_patterns_store.py`
- `src/description_normaliser.py`
- `src/normalisation_cache.py`

Check-statements description normalisation now uses the local cleaner only.
Alias learning keeps deterministic seed grouping and alias-memory updates, but
does not call provider APIs or apply saved model-generated pattern decisions.
PDF OCR now uses local PaddleOCR only; callers may still pass ``llm_wrapper``
for compatibility, but `modules/pdf_utils/pdf_utils.py` ignores it and does not
create an LLM OCR attempt.

## Provider-Policy Notes

Local Codex plugins must run without direct model-provider API calls. Codex owns
semantic judgment for plugins, with the Clara/case-notes Realtime voice flow as
the explicit exception. The vendored plugin copies of
`modules.utilities.config.select_provider` therefore fail closed instead of
mapping query steps to a model provider.

The application runtime supports OpenAI only. Provider selection remains
centralized so query steps have one auditable model mapping.

The former generic fix fallback, report-chat query steps, and check-statements
provider fallback steps were removed.

## Verification Commands

Useful checks after cleanup:

```bash
rg -n "conversation|report-chat|chat with report" modules src tests plugins
rg -n "extract_transactions_llm|LLMPageClassifier|BANK_PARSE_LLM|LLM_API_KEY" src tests
rg -n "attributeClassificationQuery|attributeDiscoveryQuery|attributeScoringQuery|pdpVisionAttributeQuery|pdpWebAttributeQuery|taxonomyGenerationQuery" modules/add_attributes modules/pdp src scripts
rg -n "select_provider\\(|query_llm_return|run_step_json|run_step_text|api.openai.com|OPENAI_API_KEY" plugins/*/scripts plugins/_shared
```

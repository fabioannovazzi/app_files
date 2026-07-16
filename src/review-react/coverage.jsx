import React, { useEffect, useMemo, useRef, useState } from "react";
import ReactDOM from "react-dom";

const apiBase = `${window.location.origin.replace(/\/$/, "")}/review`;
const ALL_BRANDS_VALUE = "__all__";
const EXCLUDED_TAXONOMY_LABELS = new Set(["n/a (not stated)", "not in taxonomy"]);
const RECORD_TYPE_OPTIONS = [
  { value: "parent", label: "Parent" },
  { value: "variant", label: "Variant" },
];
const ANALYSIS_CONFIG = {
  na: {
    label: "N/A",
    filterValue: "N/A",
    emptyBrands: "No brands with N/A examples.",
    subtitle: "Click an attribute row to fetch example products with N/A values for that attribute.",
  },
  not_in_taxonomy: {
    label: "Not in taxonomy",
    filterValue: "Not in taxonomy",
    emptyBrands: "No brands with not-in-taxonomy examples.",
    subtitle: "Click an attribute row to fetch example products with not-in-taxonomy values for that attribute.",
  },
  found: {
    label: "Found",
    filterValue: "FOUND",
    emptyBrands: "No brands with found examples.",
    subtitle: "Click an attribute row to fetch example products where that attribute has a found value.",
  },
};

function sanitizeUrl(url) {
  if (!url) return null;
  let cleaned = String(url).trim();
  cleaned = cleaned.replace(/\\u002F/gi, "/").replace(/\\\//g, "/");
  return cleaned || null;
}

function isHttpUrl(url) {
  try {
    const parsed = new URL(String(url || ""));
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch (_) {
    return false;
  }
}

function normalizeText(value) {
  if (!value) return "";
  return String(value).toLowerCase().replace(/\s+/g, " ").trim();
}

function stripWrappingQuotes(value) {
  let text = String(value || "").trim();
  while (
    text.length >= 2
    && ((text.startsWith('"') && text.endsWith('"')) || (text.startsWith("'") && text.endsWith("'")))
  ) {
    text = text.slice(1, -1).trim();
  }
  return text;
}

function isPlaceholderNotaxDetail(value) {
  const normalized = normalizeText(value);
  if (!normalized) {
    return true;
  }
  if (
    normalized === "n/a"
    || normalized === "n/a (not stated)"
    || normalized === "na"
    || normalized === "none"
    || normalized === "unknown"
    || normalized === "not stated"
    || normalized === "null"
    || normalized === "not in taxonomy"
  ) {
    return true;
  }
  return normalized.startsWith("not in taxonomy");
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeRegex(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function buildWholeWordRegex(term) {
  if (!term) {
    return null;
  }
  const escaped = escapeRegex(term);
  return new RegExp(`(^|[^a-z0-9])${escaped}([^a-z0-9]|$)`, "gi");
}

function highlightMatchedTerms(text, terms) {
  const input = String(text || "");
  const cleaned = Array.from(
    new Set(
      (terms || [])
        .map((term) => String(term || "").trim())
        .filter(Boolean),
    ),
  );
  if (!cleaned.length) {
    return escapeHtml(input);
  }

  const sortedTerms = cleaned.sort((a, b) => b.length - a.length);
  const regex = new RegExp(
    sortedTerms
      .map((term) => `(^|[^a-z0-9])${escapeRegex(term)}([^a-z0-9]|$)`)
      .join("|"),
    "gi",
  );

  let result = "";
  let lastIndex = 0;
  let match = regex.exec(input);
  while (match) {
    if (match.index > lastIndex) {
      result += escapeHtml(input.slice(lastIndex, match.index));
    }
    if (!match[0]) {
      break;
    }
    const matchText = match[0];
    const contentStart = matchText.search(/[a-z0-9]/i);
    const contentEnd = matchText.search(/[^a-z0-9][^a-z0-9]*$/i);
    const safeEnd = contentEnd === -1 ? matchText.length : contentEnd;
    const prefix = matchText.slice(0, contentStart === -1 ? 0 : contentStart);
    const content = matchText.slice(contentStart === -1 ? 0 : contentStart, safeEnd);
    const suffix = matchText.slice(safeEnd);
    result += `${escapeHtml(prefix)}<strong class=\"coverage-match-term\">${escapeHtml(content)}</strong>${escapeHtml(suffix)}`;
    lastIndex = match.index + matchText.length;
    match = regex.exec(input);
  }
  if (lastIndex < input.length) {
    result += escapeHtml(input.slice(lastIndex));
  }
  return result;
}

function buildRecordText(record) {
  const textParts = [
    record.pdp_text,
    record.product_description,
    record.description_markdown,
    record.description,
    record.variant_description,
  ];
  return normalizeText(textParts.filter(Boolean).join(" "));
}

function isExcludedTaxonomyNode(node) {
  if (!node) {
    return false;
  }
  const label = String(node.label || "").trim().toLowerCase();
  return EXCLUDED_TAXONOMY_LABELS.has(label);
}

function collectTaxonomyMatchers(nodes) {
  const matchers = [];
  (nodes || []).forEach((node) => {
    if (!node || isExcludedTaxonomyNode(node)) {
      return;
    }
    const label = String(node.label || "").trim();
    if (!label) {
      return;
    }
    const termMap = new Map();
    const addTerm = (term) => {
      const cleaned = String(term || "").trim();
      if (!cleaned) {
        return;
      }
      const normalized = normalizeText(cleaned);
      if (!normalized || termMap.has(normalized)) {
        return;
      }
      termMap.set(normalized, cleaned);
    };
    addTerm(label);
    if (Array.isArray(node.synonyms)) {
      node.synonyms.forEach(addTerm);
    }
    matchers.push({
      label,
      terms: Array.from(termMap.entries()).map(([normalized, term]) => ({ term, normalized })),
    });
  });
  return matchers;
}

function computeDeterministicMatches(records, nodes) {
  const recordSummaries = (records || []).map((record, index) => {
    const name = record.product_name || record.product || `Example ${index + 1}`;
    const pdpUrl = typeof record.pdp_url === "string" ? record.pdp_url.trim() : "";
    return {
      id: record.parent_product_id || record.product || record.parent || String(index),
      name,
      pdpUrl,
      text: buildRecordText(record),
    };
  });

  const matchers = collectTaxonomyMatchers(nodes);
  const matches = [];
  const recordMatchMap = new Map();

  matchers.forEach((matcher) => {
    const recordMatches = [];
    recordSummaries.forEach((record) => {
      if (!record.text) {
        return;
      }
      const matchedTerms = new Map();
      matcher.terms.forEach(({ term, normalized }) => {
        if (!normalized) {
          return;
        }
        const pattern = buildWholeWordRegex(normalized);
        if (pattern && pattern.test(record.text)) {
          matchedTerms.set(normalized, term);
        }
      });
      if (matchedTerms.size) {
        recordMatches.push({
          record,
          matchedTerms: Array.from(matchedTerms.values()),
        });
        const current = recordMatchMap.get(record.id) || [];
        recordMatchMap.set(
          record.id,
          Array.from(new Set(current.concat(Array.from(matchedTerms.values())))),
        );
      }
    });
    if (recordMatches.length) {
      matches.push({
        label: matcher.label,
        recordMatches,
      });
    }
  });

  return {
    totalTerms: matchers.length,
    matches,
    recordSummaries,
    recordMatchMap,
  };
}

function formatPct(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "0%";
  }
  if (value > 0 && value < 0.001) {
    return "<0.1%";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatRunAverage(value) {
  if (!Number.isFinite(value)) {
    return "0";
  }
  const rounded = Math.round(value * 10) / 10;
  if (Math.abs(rounded - Math.trunc(rounded)) < 1e-9) {
    return String(Math.trunc(rounded));
  }
  return rounded.toFixed(1);
}

function formatConfidenceValue(attribute) {
  const support = Number(attribute.confidence_support_avg);
  const total = Number(attribute.confidence_total_avg);
  if (!Number.isFinite(support) || !Number.isFinite(total) || total <= 0) {
    return "0 samples";
  }
  const ratioText = `${formatRunAverage(support)}/${formatRunAverage(total)}`;
  const pct = Number(attribute.confidence_pct);
  if (!Number.isFinite(pct)) {
    return ratioText;
  }
  return `${ratioText} (${(pct * 100).toFixed(0)}%)`;
}

function formatNumber(value, options = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "0";
  }
  return Number(value).toLocaleString(undefined, options);
}

function extractNotInTaxonomyDetail(rawValue) {
  if (rawValue === null || rawValue === undefined) {
    return "";
  }
  const text = stripWrappingQuotes(rawValue);
  if (!text) {
    return "";
  }
  const lowered = text.toLowerCase();
  if (!lowered.startsWith("not in taxonomy")) {
    return text;
  }
  let suffix = text.slice("not in taxonomy".length).trim();
  if (!suffix) {
    return "";
  }
  if (suffix.startsWith("(") && suffix.endsWith(")") && suffix.length > 2) {
    suffix = suffix.slice(1, -1).trim();
  } else if (suffix.startsWith(":") || suffix.startsWith("-")) {
    suffix = suffix.slice(1).trim();
  }
  const cleaned = stripWrappingQuotes(suffix);
  if (isPlaceholderNotaxDetail(cleaned)) {
    return "";
  }
  return cleaned;
}

function extractNotInTaxonomyExampleValue(record, attributeColumn) {
  const rawValue = attributeColumn ? record[attributeColumn] : null;
  const inlineDetail = extractNotInTaxonomyDetail(rawValue);
  if (inlineDetail) {
    return inlineDetail;
  }

  const audit = record.attribute_audit || {};
  const evidence = audit.evidence || {};
  const oovCandidate = evidence.oov_candidate;
  if (typeof oovCandidate === "string" && oovCandidate.trim()) {
    return oovCandidate.trim();
  }

  const auditValue = extractNotInTaxonomyDetail(audit.value);
  if (auditValue) {
    return auditValue;
  }

  return "";
}

function parseErrorMessage(error) {
  if (!error) {
    return "Unknown error.";
  }
  const rawMessage = error.message || String(error);
  if (!rawMessage) {
    return "Unknown error.";
  }
  try {
    const parsed = JSON.parse(rawMessage);
    if (parsed && parsed.detail) {
      return String(parsed.detail);
    }
  } catch (_) {
    // no-op
  }
  return rawMessage;
}

function buildQuery(params) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") {
      return;
    }
    if (Array.isArray(value)) {
      value.forEach((entry) => query.append(key, entry));
    } else {
      query.append(key, value);
    }
  });
  return query.toString();
}

function readInitialCoverageState() {
  const params = new URLSearchParams(window.location.search || "");
  const analysis = params.get("analysis");
  const recordType = params.get("record_type");
  return {
    retailers: params.getAll("retailer").map((value) => String(value)).filter(Boolean),
    category: String(params.get("category") || ""),
    analysis: ANALYSIS_CONFIG[analysis] ? analysis : "na",
    recordType: RECORD_TYPE_OPTIONS.some((item) => item.value === recordType) ? recordType : "parent",
    attributeId: String(params.get("attribute_id") || ""),
  };
}

async function fetchJSON(path) {
  const response = await fetch(`${apiBase}${path}`, { credentials: "include" });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed (${response.status})`);
  }
  return response.json();
}

function CoverageSegment({ label, target, active, tooltip }) {
  return (
    <button
      className="coverage-segment"
      type="button"
      aria-pressed={active ? "true" : "false"}
      data-tooltip={tooltip}
      onClick={() => {
        if (!active) {
          window.location.href = target;
        }
      }}
      disabled={active}
    >
      {label}
    </button>
  );
}

function CoveragePills({ options, selectedValues, onToggle, ariaLabel }) {
  if (!options.length) {
    return <span className="muted">No options available.</span>;
  }
  return (
    <div className="coverage-pill-group" role="group" aria-label={ariaLabel}>
      {options.map((option) => {
        const value = String(option.value);
        const selected = selectedValues.has(value);
        return (
          <button
            key={value}
            className="coverage-pill"
            type="button"
            data-value={value}
            aria-pressed={selected ? "true" : "false"}
            onClick={() => onToggle(value)}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

function TaxonomyCard({ attributeLabel, nodes, error }) {
  const filteredNodes = useMemo(
    () => (Array.isArray(nodes) ? nodes.filter((node) => !isExcludedTaxonomyNode(node)) : []),
    [nodes],
  );

  return (
    <div className="coverage-mini-card coverage-mini-card--taxonomy">
      <h3>{attributeLabel} taxonomy values</h3>
      <div className="coverage-taxonomy-list">
        {error ? <div className="coverage-empty">{error}</div> : null}
        {!error && !filteredNodes.length ? (
          <div className="coverage-empty">No taxonomy values found for this attribute.</div>
        ) : null}
        {!error
          ? filteredNodes.map((node, index) => (
            <div key={`${node.label}-${index}`} className="coverage-taxonomy-row" style={{ paddingLeft: `${Number(node.depth || 0) * 16}px` }}>
              <div className="coverage-taxonomy-label">{node.label}</div>
              {Array.isArray(node.synonyms) && node.synonyms.length ? (
                <div className="coverage-taxonomy-synonyms">Synonyms: {node.synonyms.join(", ")}</div>
              ) : null}
            </div>
          ))
          : null}
      </div>
    </div>
  );
}

function DeterministicCard({ results }) {
  const matchedTerms = results.matches || [];
  return (
    <div className="coverage-mini-card coverage-mini-card--deterministic">
      <h3>Deterministic scan</h3>
      <p className="coverage-mini-subtitle">
        {matchedTerms.length} taxonomy labels appear in the PDPs of the selected examples.
      </p>
      <div className="coverage-deterministic-list">
        {!matchedTerms.length ? <div className="coverage-empty">No taxonomy values were found in the selected PDP text.</div> : null}
        {matchedTerms.map((match) => (
          <div key={match.label} className="coverage-deterministic-row">
            <div className="coverage-deterministic-term">{match.label} ({match.recordMatches.length})</div>
            <div className="coverage-deterministic-examples">
              {match.recordMatches.map(({ record, matchedTerms: terms }) => (
                <div key={`${match.label}-${record.id}`} className="coverage-deterministic-item">
                  <div className="coverage-deterministic-name-wrapper">
                    {record.pdpUrl ? (
                      <a href={record.pdpUrl} target="_blank" rel="noopener noreferrer" className="coverage-deterministic-name">
                        {record.name}
                      </a>
                    ) : (
                      <span className="coverage-deterministic-name">{record.name}</span>
                    )}
                  </div>
                  {terms && terms.length ? (
                    <div className="coverage-deterministic-badges">
                      {terms.map((term) => (
                        <span key={`${record.id}-${term}`} className="coverage-deterministic-badge">
                          {term}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ExampleCard({
  record,
  index,
  analysisMode,
  attributeColumn,
  highlightedHtml,
}) {
  const brand = record.brand || "Unknown brand";
  const name = record.product_name || record.product || "Unknown product";
  const pdpUrl = typeof record.pdp_url === "string" ? record.pdp_url.trim() : "";

  const hero = sanitizeUrl(record.hero_image_url);
  const swatch = sanitizeUrl(record.swatch_image_url);
  const parentId = record.parent_product_id || record.product || record.parent;
  const variantId = record.variant_id || record.variant;
  let imageUrl = hero || swatch;
  if (!imageUrl && parentId) {
    const params = new URLSearchParams();
    if (variantId) params.append("variant", variantId);
    imageUrl = `${apiBase}/images/${parentId}${params.toString() ? `?${params.toString()}` : ""}`;
  }

  const pdpText =
    record.pdp_text
    || record.product_description
    || record.description_markdown
    || record.description
    || record.variant_description
    || "No PDP text available.";

  const renderAttributeAudit = () => {
    const audit = record.attribute_audit;
    if (!audit) {
      return <div className="coverage-example-audit">Audit unavailable.</div>;
    }
    const source = audit.source || "unknown";
    const rule = audit.decision_rule || "unknown";
    const evidence = audit.evidence || {};
    const rows = [];
    rows.push({ key: "source", label: "Source", value: source, asLink: false });
    rows.push({ key: "decision", label: "Decision", value: rule, asLink: false });
    if (audit.promoted !== undefined && audit.promoted !== null) {
      rows.push({ key: "promoted", label: "Promoted", value: audit.promoted ? "yes" : "no", asLink: false });
    }

    const supportRunsRaw = Number(audit.support_runs);
    const totalRunsRaw = Number(audit.total_runs);
    if (Number.isFinite(supportRunsRaw) && Number.isFinite(totalRunsRaw) && totalRunsRaw > 0) {
      const supportRuns = Math.max(0, Math.trunc(supportRunsRaw));
      const totalRuns = Math.max(0, Math.trunc(totalRunsRaw));
      const availableRunsRaw = Number(audit.available_runs);
      const availableRuns = Number.isFinite(availableRunsRaw) && availableRunsRaw > 0
        ? Math.max(0, Math.trunc(availableRunsRaw))
        : totalRuns;
      const displayTotalRuns = Math.max(totalRuns, availableRuns);
      const displayAgreementRate = supportRuns / displayTotalRuns;
      rows.push({
        key: "confirmed",
        label: "Confirmed",
        value: `${supportRuns}/${displayTotalRuns} (${(displayAgreementRate * 100).toFixed(0)}%)`,
        asLink: false,
      });
    }

    const usedKeys = new Set();
    if (evidence.confidence !== undefined && evidence.confidence !== null) {
      rows.push({ key: "confidence", label: "Confidence", value: evidence.confidence, asLink: false });
      usedKeys.add("confidence");
    }
    if (evidence.image_source) {
      rows.push({ key: "image_source", label: "Image source", value: evidence.image_source, asLink: false });
      usedKeys.add("image_source");
    }
    if (evidence.image_path) {
      rows.push({ key: "image_path", label: "Image path", value: evidence.image_path, asLink: false });
      usedKeys.add("image_path");
    }
    if (evidence.hero_image_url) {
      const heroImageUrl = sanitizeUrl(evidence.hero_image_url) || evidence.hero_image_url;
      rows.push({ key: "hero_image_url", label: "Image URL", value: heroImageUrl, asLink: isHttpUrl(heroImageUrl) });
      usedKeys.add("hero_image_url");
    }
    if (evidence.evidence_url) {
      const evidenceUrl = sanitizeUrl(evidence.evidence_url) || evidence.evidence_url;
      rows.push({ key: "evidence_url", label: "Evidence URL", value: evidenceUrl, asLink: isHttpUrl(evidenceUrl) });
      usedKeys.add("evidence_url");
    }

    Object.entries(evidence).forEach(([key, value]) => {
      if (usedKeys.has(key) || key === "stage_source" || value === null || value === undefined || value === "") {
        return;
      }
      rows.push({ key: `extra_${key}`, label: key, value, asLink: false });
    });

    return (
      <div className="coverage-example-audit">
        {rows.map((row) => (
          <div key={row.key}>
            {row.label}: {row.asLink ? (
              <a href={String(row.value)} target="_blank" rel="noopener noreferrer">{String(row.value)}</a>
            ) : (
              String(row.value)
            )}
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="coverage-mini-card" key={`${record.parent_product_id || record.product || index}`}>
      <div><strong>{brand}</strong></div>
      <div className="coverage-example-image-wrapper">
        {imageUrl ? <img src={imageUrl} alt="" className="coverage-example-image" /> : null}
      </div>
      <div className="coverage-example-name">
        {pdpUrl ? (
          <a href={pdpUrl} target="_blank" rel="noopener noreferrer" style={{ color: "inherit", textDecoration: "underline" }}>
            {name}
          </a>
        ) : (
          name
        )}
      </div>
      {analysisMode === "found" || analysisMode === "not_in_taxonomy" ? (
        <div className="coverage-example-meta">
          <div className="coverage-example-label">
            {analysisMode === "not_in_taxonomy" ? "Not in taxonomy value" : "Selected value"}
          </div>
          <div className="coverage-example-text">
            {analysisMode === "not_in_taxonomy"
              ? (extractNotInTaxonomyExampleValue(record, attributeColumn) || "N/A")
              : (attributeColumn && record[attributeColumn] ? String(record[attributeColumn]) : "N/A")}
          </div>
        </div>
      ) : null}
      {record.attribute_audit ? renderAttributeAudit() : null}
      <div className="coverage-example-text" dangerouslySetInnerHTML={{ __html: highlightedHtml || escapeHtml(pdpText) }} />
    </div>
  );
}

function App() {
  const initialCoverageState = readInitialCoverageState();
  const [retailerOptions, setRetailerOptions] = useState([]);
  const [categoryOptions, setCategoryOptions] = useState([]);
  const [selectedRetailers, setSelectedRetailers] = useState(initialCoverageState.retailers);
  const [selectedCategory, setSelectedCategory] = useState(initialCoverageState.category);
  const [selectedRecordType, setSelectedRecordType] = useState(initialCoverageState.recordType);
  const [selectedAnalysis, setSelectedAnalysis] = useState(initialCoverageState.analysis);

  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const [totalRecords, setTotalRecords] = useState(0);
  const [coverageAttributes, setCoverageAttributes] = useState([]);

  const [selectedExampleAttribute, setSelectedExampleAttribute] = useState(null);
  const [brandOptions, setBrandOptions] = useState([]);
  const [selectedBrands, setSelectedBrands] = useState([ALL_BRANDS_VALUE]);

  const [exampleRecords, setExampleRecords] = useState([]);
  const [taxonomyNodes, setTaxonomyNodes] = useState([]);
  const [taxonomyError, setTaxonomyError] = useState("");

  const coverageTimerRef = useRef(null);
  const pendingAttributeIdRef = useRef(initialCoverageState.attributeId);

  const selectedRetailersSet = useMemo(() => new Set(selectedRetailers.map(String)), [selectedRetailers]);
  const selectedBrandsSet = useMemo(() => new Set(selectedBrands.map(String)), [selectedBrands]);
  const selectedAnalysisConfig = useMemo(
    () => ANALYSIS_CONFIG[selectedAnalysis] || ANALYSIS_CONFIG.na,
    [selectedAnalysis],
  );

  const sortedCoverageAttributes = useMemo(() => {
    const sorted = [...coverageAttributes];
    sorted.sort((a, b) => {
      const filledA = Number.isFinite(Number(a.filled_pct)) ? Number(a.filled_pct) : 0;
      const filledB = Number.isFinite(Number(b.filled_pct)) ? Number(b.filled_pct) : 0;
      if (filledB !== filledA) {
        return filledB - filledA;
      }
      return String(a.label || "").localeCompare(String(b.label || ""), undefined, { sensitivity: "base" });
    });
    return sorted;
  }, [coverageAttributes]);

  const deterministicResults = useMemo(
    () => computeDeterministicMatches(exampleRecords, taxonomyNodes),
    [exampleRecords, taxonomyNodes],
  );

  const brandEmptyMessage = useMemo(() => {
    if (!selectedExampleAttribute) {
      return "Select an attribute to see relevant brands.";
    }
    if (!selectedRetailers.length || !selectedCategory) {
      return "Select retailers and a category first.";
    }
    return selectedAnalysisConfig.emptyBrands;
  }, [selectedExampleAttribute, selectedRetailers, selectedCategory, selectedAnalysisConfig]);

  const clearExamplesAndBrands = (message = "") => {
    setSelectedExampleAttribute(null);
    setBrandOptions([]);
    setSelectedBrands([ALL_BRANDS_VALUE]);
    setExampleRecords([]);
    setTaxonomyNodes([]);
    setTaxonomyError("");
    if (message) {
      setStatusMessage(message);
    }
  };

  const loadRetailers = async () => {
    try {
      const data = await fetchJSON("/retailers");
      const options = (data.retailers || []).map((value) => ({ value: String(value), label: String(value) }));
      setRetailerOptions(options);
      if (!options.length) {
        setSelectedRetailers([]);
        setErrorMessage("No retailers available.");
        return;
      }
      setSelectedRetailers((current) => {
        const allowed = new Set(options.map((opt) => opt.value));
        const kept = current.filter((value) => allowed.has(String(value)));
        if (kept.length) {
          return kept;
        }
        const preferred = options.find((opt) => String(opt.value).trim().toLowerCase() === "ulta");
        return [preferred ? preferred.value : options[0].value];
      });
      setErrorMessage("");
    } catch (error) {
      setErrorMessage(parseErrorMessage(error));
    }
  };

  const loadCategories = async (retailers) => {
    if (!retailers.length) {
      setCategoryOptions([]);
      setSelectedCategory("");
      setErrorMessage("Select at least one retailer first.");
      return;
    }
    try {
      const query = buildQuery({ retailer: retailers });
      const data = await fetchJSON(`/categories?${query}`);
      const options = (data.categories || []).map((item) => ({
        value: String(item.key || item.value || item),
        label: String(item.label || item.value || item),
      }));
      setCategoryOptions(options);
      setSelectedCategory((current) => {
        if (options.some((opt) => opt.value === current)) {
          return current;
        }
        return options.length ? options[0].value : "";
      });
      setErrorMessage("");
    } catch (error) {
      setCategoryOptions([]);
      setSelectedCategory("");
      setErrorMessage(parseErrorMessage(error));
    }
  };

  const loadCoverage = async () => {
    const retailers = [...selectedRetailers];
    if (!retailers.length) {
      setErrorMessage("Select at least one retailer before loading coverage.");
      return;
    }
    if (!selectedCategory) {
      setErrorMessage("Select a category before loading coverage.");
      return;
    }
    setErrorMessage("");
    setStatusMessage("Loading coverage…");
    try {
      const query = buildQuery({
        retailer: retailers,
        category: [selectedCategory],
        record_type: selectedRecordType,
      });
      const data = await fetchJSON(`/coverage?${query}`);
      setTotalRecords(Number(data.total_records || 0));
      setCoverageAttributes(Array.isArray(data.attributes) ? data.attributes : []);
      clearExamplesAndBrands();
      setStatusMessage("Coverage loaded.");
    } catch (error) {
      setErrorMessage(parseErrorMessage(error));
      setStatusMessage("");
    }
  };

  const loadRelevantBrands = async (attributeId) => {
    if (!attributeId) {
      setBrandOptions([]);
      setSelectedBrands([ALL_BRANDS_VALUE]);
      return;
    }
    if (!selectedRetailers.length || !selectedCategory) {
      setBrandOptions([]);
      setSelectedBrands([ALL_BRANDS_VALUE]);
      return;
    }
    try {
      const query = buildQuery({
        retailer: selectedRetailers,
        category: [selectedCategory],
        record_type: selectedRecordType,
        attribute_id: attributeId,
        analysis: selectedAnalysis,
      });
      const data = await fetchJSON(`/brands/relevant?${query}`);
      const options = (data.brands || []).map((value) => ({ value: String(value), label: String(value) }));
      setBrandOptions(options);
      setSelectedBrands((current) => {
        const available = new Set(options.map((opt) => opt.value));
        let next = current.filter((value) => value === ALL_BRANDS_VALUE || available.has(String(value)));
        if (!next.length) {
          next = [ALL_BRANDS_VALUE];
        } else if (next.some((value) => value !== ALL_BRANDS_VALUE)) {
          next = next.filter((value) => value !== ALL_BRANDS_VALUE);
        }
        return Array.from(new Set(next));
      });
    } catch (error) {
      setErrorMessage(parseErrorMessage(error));
    }
  };

  const fetchTaxonomyBranch = async (attributeId) => {
    if (!attributeId || !selectedCategory) {
      return { nodes: [] };
    }
    const query = buildQuery({
      category: [selectedCategory],
      attribute_id: attributeId,
    });
    return fetchJSON(`/taxonomy/branch?${query}`);
  };

  const fetchExamples = async (attribute) => {
    if (!attribute || !attribute.id || !selectedCategory) {
      return;
    }
    const analysisConfig = selectedAnalysisConfig;
    setStatusMessage(`Loading ${analysisConfig.label} examples for ${attribute.label}…`);
    setErrorMessage("");

    const filters = [`${attribute.id}:${analysisConfig.filterValue}`];
    const selectedBrandList = selectedBrands.filter((brand) => brand !== ALL_BRANDS_VALUE);
    const query = buildQuery({
      retailer: selectedRetailers,
      brand: selectedBrandList,
      category: [selectedCategory],
      record_type: selectedRecordType,
      filters,
      audit_attribute_id: selectedAnalysis === "found" || selectedAnalysis === "not_in_taxonomy" ? attribute.id : "",
      limit: "12",
    });

    const [recordsResult, taxonomyResult] = await Promise.allSettled([
      fetchJSON(`/records?${query}`),
      fetchTaxonomyBranch(attribute.id),
    ]);

    const records = recordsResult.status === "fulfilled" ? recordsResult.value.records || [] : [];
    const nodes = taxonomyResult.status === "fulfilled" ? taxonomyResult.value.nodes || [] : [];

    if (recordsResult.status === "rejected") {
      setErrorMessage(parseErrorMessage(recordsResult.reason));
    }

    let branchError = "";
    if (taxonomyResult.status === "rejected") {
      branchError = `Unable to load taxonomy values: ${parseErrorMessage(taxonomyResult.reason)}`;
      setErrorMessage(branchError);
    }

    setExampleRecords(records);
    setTaxonomyNodes(nodes);
    setTaxonomyError(branchError);
    setStatusMessage(`Loaded ${records.length} examples.`);
  };

  useEffect(() => {
    loadRetailers();
  }, []);

  useEffect(() => {
    loadCategories(selectedRetailers);
  }, [selectedRetailers.join("|")]);

  useEffect(() => {
    clearExamplesAndBrands("Select an attribute to see relevant brands.");
  }, [selectedRetailers.join("|"), selectedCategory, selectedRecordType]);

  useEffect(() => {
    if (coverageTimerRef.current) {
      window.clearTimeout(coverageTimerRef.current);
    }
    coverageTimerRef.current = window.setTimeout(() => {
      loadCoverage();
    }, 300);

    return () => {
      if (coverageTimerRef.current) {
        window.clearTimeout(coverageTimerRef.current);
        coverageTimerRef.current = null;
      }
    };
  }, [selectedRetailers.join("|"), selectedCategory, selectedRecordType]);

  useEffect(() => {
    if (!selectedExampleAttribute) {
      return;
    }
    loadRelevantBrands(selectedExampleAttribute.id);
  }, [
    selectedExampleAttribute ? String(selectedExampleAttribute.id) : "",
    selectedAnalysis,
    selectedRetailers.join("|"),
    selectedCategory,
    selectedRecordType,
  ]);

  useEffect(() => {
    if (!selectedExampleAttribute) {
      return;
    }
    fetchExamples(selectedExampleAttribute).catch((error) => {
      setErrorMessage(parseErrorMessage(error));
      setStatusMessage("");
    });
  }, [
    selectedExampleAttribute ? String(selectedExampleAttribute.id) : "",
    selectedExampleAttribute ? String(selectedExampleAttribute.column || "") : "",
    selectedAnalysis,
    selectedRetailers.join("|"),
    selectedCategory,
    selectedRecordType,
    selectedBrands.join("|"),
  ]);

  useEffect(() => {
    if (!pendingAttributeIdRef.current || !coverageAttributes.length) {
      return;
    }
    const targetId = String(pendingAttributeIdRef.current);
    const matched = coverageAttributes.find((attribute) => String(attribute.id) === targetId);
    pendingAttributeIdRef.current = "";
    if (matched) {
      onSelectAttribute(matched);
    }
  }, [coverageAttributes]);

  const onToggleRetailer = (value) => {
    setSelectedRetailers((current) => {
      const set = new Set(current.map(String));
      const token = String(value);
      if (set.has(token)) {
        if (set.size === 1) {
          return current;
        }
        set.delete(token);
      } else {
        set.add(token);
      }
      return Array.from(set);
    });
  };

  const onToggleRecordType = (value) => {
    if (selectedRecordType === value) {
      return;
    }
    setSelectedRecordType(value);
  };

  const onToggleCategory = (value) => {
    if (selectedCategory === value) {
      return;
    }
    setSelectedCategory(value);
  };

  const onToggleAnalysis = (value) => {
    if (!ANALYSIS_CONFIG[value] || selectedAnalysis === value) {
      return;
    }
    setSelectedAnalysis(value);
  };

  const onToggleBrand = (value) => {
    const token = String(value);
    if (token === ALL_BRANDS_VALUE) {
      setSelectedBrands([ALL_BRANDS_VALUE]);
      return;
    }
    setSelectedBrands((current) => {
      const set = new Set(current.filter((item) => item !== ALL_BRANDS_VALUE).map(String));
      if (set.has(token)) {
        set.delete(token);
      } else {
        set.add(token);
      }
      if (!set.size) {
        return [ALL_BRANDS_VALUE];
      }
      return Array.from(set);
    });
  };

  const onSelectAttribute = (attribute) => {
    setSelectedExampleAttribute({
      id: String(attribute.id),
      label: String(attribute.label || attribute.id),
      column: String(attribute.column || ""),
    });
  };

  return (
    <div>
      <div className="coverage-toolbar">
        <section className="coverage-card coverage-toolbar-card" aria-label="Review settings">
          <div className="coverage-card-title">Settings</div>
          <div className="coverage-subcard coverage-subcard--views">
            <div className="coverage-toggle" role="tablist">
              <CoverageSegment
                label="Catalog"
                target="/review/page"
                active={false}
                tooltip="See filtered products"
              />
              <CoverageSegment
                label="Coverage"
                target="/review/coverage/page"
                active
                tooltip="Explore attribute coverage and N/A examples"
              />
              <CoverageSegment
                label="Explicit attributes"
                target="/review/explicit-rules/page"
                active={false}
                tooltip="Review explicit attributes"
              />
              <CoverageSegment
                label="Issues"
                target="/review/issues/page"
                active={false}
                tooltip="Find suspicious attribute issues and inspect them in Coverage"
              />
            </div>
          </div>

          <div className="coverage-subcard coverage-subcard--analysis">
            <CoveragePills
              ariaLabel="Analyze coverage"
              options={[
                { value: "na", label: "N/A" },
                { value: "not_in_taxonomy", label: "Not in taxonomy" },
                { value: "found", label: "Found" },
              ]}
              selectedValues={new Set([selectedAnalysis])}
              onToggle={onToggleAnalysis}
            />
          </div>
        </section>
      </div>

      <div className="coverage-layout">
        <section className="coverage-card coverage-card--filters">
          <div className="coverage-card-title">Filters &amp; scope</div>
          <div className="coverage-form-grid">
            <div className="coverage-field coverage-subcard">
              <label className="coverage-label">Record type</label>
              <CoveragePills
                ariaLabel="Record type"
                options={RECORD_TYPE_OPTIONS}
                selectedValues={new Set([selectedRecordType])}
                onToggle={onToggleRecordType}
              />
            </div>

            <div className="coverage-field coverage-subcard">
              <label className="coverage-label">Retailer</label>
              <CoveragePills
                ariaLabel="Retailer sources"
                options={retailerOptions}
                selectedValues={selectedRetailersSet}
                onToggle={onToggleRetailer}
              />
            </div>

            <div className="coverage-field coverage-subcard">
              <label className="coverage-label">Category</label>
              <CoveragePills
                ariaLabel="Category selection"
                options={categoryOptions}
                selectedValues={new Set(selectedCategory ? [selectedCategory] : [])}
                onToggle={onToggleCategory}
              />
            </div>
          </div>

          <div className="coverage-status">
            <span className="muted">{statusMessage}</span>
            <div className="error">{errorMessage}</div>
          </div>
        </section>

        <section className="coverage-card coverage-card--summary">
          <div className="coverage-card-title">Coverage snapshot</div>
          <p className="coverage-subtitle">{selectedAnalysisConfig.subtitle}</p>

          <div className="coverage-summary">
            <div className="coverage-mini-card coverage-summary-card">
              <h3>Totals</h3>
              <div className="coverage-summary-grid">
                <div className="coverage-summary-item">
                  <div className="coverage-summary-label">Records</div>
                  <div className="coverage-summary-value">{formatNumber(totalRecords)}</div>
                </div>
              </div>
            </div>
          </div>

          <table className="coverage-table">
            <thead>
              <tr>
                <th>Attribute</th>
                <th>Filled %</th>
                <th>N/A %</th>
                <th>Not in taxonomy %</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {!sortedCoverageAttributes.length ? (
                <tr>
                  <td colSpan={5}>No coverage data.</td>
                </tr>
              ) : null}
              {sortedCoverageAttributes.map((attr) => {
                const selected = selectedExampleAttribute && String(selectedExampleAttribute.id) === String(attr.id);
                return (
                  <tr
                    key={String(attr.id)}
                    data-attr-id={String(attr.id)}
                    className={selected ? "coverage-table-row--selected" : ""}
                    aria-selected={selected ? "true" : "false"}
                    onClick={() => onSelectAttribute(attr)}
                  >
                    <td>{attr.label}</td>
                    <td>{formatPct(attr.filled_pct)}</td>
                    <td>{formatPct(attr.missing_pct)}</td>
                    <td>{formatPct(attr.not_in_taxonomy_pct)}</td>
                    <td>{formatConfidenceValue(attr)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>

        <section className="coverage-card coverage-card--brand">
          <div className="coverage-field">
            <label className="coverage-label">Brand</label>
            {!brandOptions.length ? (
              <span className="muted">{brandEmptyMessage}</span>
            ) : (
              <CoveragePills
                ariaLabel="Brand selection"
                options={[{ value: ALL_BRANDS_VALUE, label: "All" }, ...brandOptions]}
                selectedValues={selectedBrandsSet}
                onToggle={onToggleBrand}
              />
            )}
          </div>
        </section>

        <section className="coverage-card coverage-card--examples">
          <div className="coverage-examples-grid">
            {selectedExampleAttribute ? (
              <>
                <TaxonomyCard
                  attributeLabel={selectedExampleAttribute.label}
                  nodes={taxonomyNodes}
                  error={taxonomyError}
                />
                <DeterministicCard results={deterministicResults} />
                {!exampleRecords.length ? <div className="coverage-empty">No examples found for this attribute.</div> : null}
                {exampleRecords.map((record, index) => {
                  const recordId = record.parent_product_id || record.product || record.parent || String(index);
                  const matchedTerms = deterministicResults.recordMatchMap.get(recordId);
                  const highlightedHtml = highlightMatchedTerms(
                    record.pdp_text
                      || record.product_description
                      || record.description_markdown
                      || record.description
                      || record.variant_description
                      || "No PDP text available.",
                    matchedTerms,
                  );
                  return (
                    <ExampleCard
                      key={`${recordId}-${index}`}
                      record={record}
                      index={index}
                      analysisMode={selectedAnalysis}
                      attributeColumn={selectedExampleAttribute.column || ""}
                      highlightedHtml={highlightedHtml}
                    />
                  );
                })}
              </>
            ) : (
              <div className="coverage-empty">Select an attribute row to fetch examples.</div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

const rootEl = document.getElementById("reactCoverageApp");
ReactDOM.createRoot(rootEl).render(<App />);

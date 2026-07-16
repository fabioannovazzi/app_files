(() => {
  const apiBase = `${window.location.origin.replace(/\/$/, "")}/review`;
  const retailerPills = document.getElementById("retailerPills");
  const brandPills = document.getElementById("brandPills");
  const recordTypePills = document.getElementById("recordTypePills");
  const categoryPills = document.getElementById("categoryPills");
  const analysisPills = document.getElementById("analysisPills");
  const statusMessage = document.getElementById("statusMessage");
  const errorMessage = document.getElementById("errorMessage");
  const coverageTableBody = document.querySelector("#coverageTable tbody");
  const summaryCards = document.getElementById("summaryCards");
  const coverageSubtitle = document.getElementById("coverageSubtitle");
  const examplesContainer = document.getElementById("examplesContainer");
  const viewButtons = document.querySelectorAll("[data-review-view]");
  const EXCLUDED_TAXONOMY_LABELS = new Set(["n/a (not stated)", "not in taxonomy"]);
  const ANALYSIS_CONFIG = {
    na: {
      label: "N/A",
      filterValue: "N/A",
      emptyBrands: "No brands with N/A examples.",
      subtitle:
        "Click an attribute row to fetch example products with N/A values for that attribute.",
    },
    not_in_taxonomy: {
      label: "Not in taxonomy",
      filterValue: "Not in taxonomy",
      emptyBrands: "No brands with not-in-taxonomy examples.",
      subtitle:
        "Click an attribute row to fetch example products with not-in-taxonomy values for that attribute.",
    },
    found: {
      label: "Found",
      filterValue: "FOUND",
      emptyBrands: "No brands with found examples.",
      subtitle:
        "Click an attribute row to fetch example products where that attribute has a found value.",
    },
  };

  let lastCoverage = null;
  let selectedRetailers = new Set();
  let selectedRecordType = "parent";
  let selectedCategory = "";
  const ALL_BRANDS_VALUE = "__all__";
  let selectedBrands = new Set([ALL_BRANDS_VALUE]);
  let selectedAnalysis = "na";
  let selectedExampleAttribute = null;
  let coverageLoadTimer = null;

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
      text.length >= 2 &&
      ((text.startsWith('"') && text.endsWith('"')) || (text.startsWith("'") && text.endsWith("'")))
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
      normalized === "n/a" ||
      normalized === "n/a (not stated)" ||
      normalized === "na" ||
      normalized === "none" ||
      normalized === "unknown" ||
      normalized === "not stated" ||
      normalized === "null" ||
      normalized === "not in taxonomy"
    ) {
      return true;
    }
    return normalized.startsWith("not in taxonomy");
  }

  function getAnalysisConfig(value) {
    const key = value || selectedAnalysis;
    return ANALYSIS_CONFIG[key] || ANALYSIS_CONFIG.na;
  }

  function renderCoverageSubtitle() {
    if (!coverageSubtitle) {
      return;
    }
    coverageSubtitle.textContent = getAnalysisConfig().subtitle;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
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
    const cleaned = Array.from(
      new Set(
        (terms || [])
          .map((term) => String(term || "").trim())
          .filter(Boolean),
      ),
    );
    if (!cleaned.length) {
      return escapeHtml(text);
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
    let match = regex.exec(text);
    while (match) {
      if (match.index > lastIndex) {
        result += escapeHtml(text.slice(lastIndex, match.index));
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
      result += `${escapeHtml(prefix)}<strong class="coverage-match-term">${escapeHtml(content)}</strong>${escapeHtml(suffix)}`;
      lastIndex = match.index + matchText.length;
      match = regex.exec(text);
    }
    if (lastIndex < text.length) {
      result += escapeHtml(text.slice(lastIndex));
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

  function renderDeterministicSummary(results) {
    const summaryCard = document.createElement("div");
    summaryCard.className = "coverage-mini-card coverage-mini-card--deterministic";
    const matchedTerms = results.matches || [];
    summaryCard.innerHTML = `
      <h3>Deterministic scan</h3>
      <p class="coverage-mini-subtitle">
        ${matchedTerms.length} taxonomy labels appear in the PDPs of the selected examples.
      </p>
    `;

    const list = document.createElement("div");
    list.className = "coverage-deterministic-list";
    if (!matchedTerms.length) {
      const empty = document.createElement("div");
      empty.className = "coverage-empty";
      empty.textContent = "No taxonomy values were found in the selected PDP text.";
      list.appendChild(empty);
    } else {
      matchedTerms.forEach((match) => {
        const row = document.createElement("div");
        row.className = "coverage-deterministic-row";
        const header = document.createElement("div");
        header.className = "coverage-deterministic-term";
        header.textContent = `${match.label} (${match.recordMatches.length})`;
        row.appendChild(header);
        const examples = document.createElement("div");
        examples.className = "coverage-deterministic-examples";
        match.recordMatches.forEach(({ record, matchedTerms }) => {
          const item = document.createElement("div");
          item.className = "coverage-deterministic-item";
          const nameWrapper = document.createElement("div");
          nameWrapper.className = "coverage-deterministic-name-wrapper";
          const name = record.name;
          if (record.pdpUrl) {
            const link = document.createElement("a");
            link.href = record.pdpUrl;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            link.textContent = name;
            link.className = "coverage-deterministic-name";
            nameWrapper.appendChild(link);
          } else {
            const span = document.createElement("span");
            span.textContent = name;
            span.className = "coverage-deterministic-name";
            nameWrapper.appendChild(span);
          }
          item.appendChild(nameWrapper);
          if (matchedTerms.length) {
            const badges = document.createElement("div");
            badges.className = "coverage-deterministic-badges";
            matchedTerms.forEach((term) => {
              const badge = document.createElement("span");
              badge.className = "coverage-deterministic-badge";
              badge.textContent = term;
              badges.appendChild(badge);
            });
            item.appendChild(badges);
          }
          examples.appendChild(item);
        });
        row.appendChild(examples);
        list.appendChild(row);
      });
    }
    summaryCard.appendChild(list);
    examplesContainer.appendChild(summaryCard);
  }

  async function fetchJSON(path) {
    const response = await fetch(`${apiBase}${path}`, { credentials: "include" });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `Request failed (${response.status})`);
    }
    return response.json();
  }

  function setStatus(message) {
    statusMessage.textContent = message || "";
  }

  function setError(message) {
    errorMessage.textContent = message || "";
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
        return parsed.detail;
      }
    } catch (parseError) {
      void parseError;
    }
    return rawMessage;
  }

  function isExcludedTaxonomyNode(node) {
    if (!node) {
      return false;
    }
    const label = String(node.label || "").trim().toLowerCase();
    return EXCLUDED_TAXONOMY_LABELS.has(label);
  }

  function renderCategoryPills(categories) {
    categoryPills.innerHTML = "";
    if (!categories.length) {
      const empty = document.createElement("span");
      empty.className = "muted";
      empty.textContent = "No categories available.";
      categoryPills.appendChild(empty);
      selectedCategory = "";
      return;
    }

    const values = categories.map((item) => String(item.key || item.value || item));
    const available = new Set(values);
    if (!available.has(String(selectedCategory))) {
      const first = categories[0].key || categories[0].value || categories[0];
      selectedCategory = String(first);
    }

    categories.forEach((item) => {
      const value = item.key || item.value || item;
      const label = item.label || item;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "coverage-pill";
      button.dataset.value = value;
      button.setAttribute("aria-pressed", selectedCategory === String(value) ? "true" : "false");
      button.textContent = label;
      button.addEventListener("click", () => {
        const valueKey = String(value);
        if (selectedCategory === valueKey) {
          return;
        }
        selectedCategory = valueKey;
        Array.from(categoryPills.querySelectorAll(".coverage-pill")).forEach((pill) => {
          pill.setAttribute("aria-pressed", pill.dataset.value === valueKey ? "true" : "false");
        });
        resetExamplesAndBrands("Select an attribute to see relevant brands.");
        scheduleCoverageLoad();
      });
      categoryPills.appendChild(button);
    });
    scheduleCoverageLoad();
  }

  function renderRecordTypePills(options) {
    recordTypePills.innerHTML = "";
    if (!options.length) {
      const empty = document.createElement("span");
      empty.className = "muted";
      empty.textContent = "No record types available.";
      recordTypePills.appendChild(empty);
      selectedRecordType = "parent";
      return;
    }

    const allowed = new Set(options.map((option) => String(option.value || option)));
    if (!allowed.has(selectedRecordType)) {
      const first = options[0].value || options[0];
      selectedRecordType = String(first);
    }

    options.forEach((option) => {
      const value = option.value || option;
      const label = option.label || option;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "coverage-pill";
      button.dataset.value = value;
      button.setAttribute("aria-pressed", selectedRecordType === String(value) ? "true" : "false");
      button.textContent = label;
      button.addEventListener("click", () => {
        const valueKey = String(value);
        if (selectedRecordType === valueKey) {
          return;
        }
        selectedRecordType = valueKey;
        Array.from(recordTypePills.querySelectorAll(".coverage-pill")).forEach((pill) => {
          pill.setAttribute("aria-pressed", pill.dataset.value === valueKey ? "true" : "false");
        });
        refreshBrandsForSelection();
        refreshExamplesForSelection();
        scheduleCoverageLoad();
      });
      recordTypePills.appendChild(button);
    });
  }

  function wireAnalysisPills() {
    if (!analysisPills) {
      return;
    }
    const buttons = Array.from(analysisPills.querySelectorAll(".coverage-pill"));
    if (!buttons.length) {
      return;
    }
    if (!ANALYSIS_CONFIG[selectedAnalysis]) {
      selectedAnalysis = "na";
    }
    renderCoverageSubtitle();
    buttons.forEach((button) => {
      const value = button.dataset.value || "";
      button.setAttribute("aria-pressed", value === selectedAnalysis ? "true" : "false");
      button.addEventListener("click", () => {
        if (!value || value === selectedAnalysis) {
          return;
        }
        selectedAnalysis = value;
        renderCoverageSubtitle();
        buttons.forEach((pill) => {
          pill.setAttribute("aria-pressed", pill.dataset.value === selectedAnalysis ? "true" : "false");
        });
        refreshBrandsForSelection();
        refreshExamplesForSelection();
      });
    });
  }

  function renderRetailerPills(retailers) {
    retailerPills.innerHTML = "";
    if (!retailers.length) {
      const empty = document.createElement("span");
      empty.className = "muted";
      empty.textContent = "No retailers available.";
      retailerPills.appendChild(empty);
      selectedRetailers = new Set();
      return;
    }

    const values = retailers.map((item) => String(item.value || item));
    const available = new Set(values);
    selectedRetailers = new Set(Array.from(selectedRetailers).filter((value) => available.has(String(value))));
    const preferred = retailers.find(
      (item) => String(item.value || item).trim().toLowerCase() === "ulta",
    );
    const defaultValue = preferred ? preferred.value || preferred : retailers[0].value || retailers[0];
    if (!selectedRetailers.size) {
      selectedRetailers.add(String(defaultValue));
    }

    retailers.forEach((item) => {
      const value = item.value || item;
      const label = item.label || item;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "coverage-pill";
      button.dataset.value = value;
      button.setAttribute("aria-pressed", selectedRetailers.has(String(value)) ? "true" : "false");
      button.textContent = label;
      button.addEventListener("click", () => {
        const valueKey = String(value);
        if (selectedRetailers.has(valueKey) && selectedRetailers.size === 1) {
          return;
        }
        if (selectedRetailers.has(valueKey)) {
          selectedRetailers.delete(valueKey);
        } else {
          selectedRetailers.add(valueKey);
        }
        Array.from(retailerPills.querySelectorAll(".coverage-pill")).forEach((pill) => {
          pill.setAttribute("aria-pressed", selectedRetailers.has(String(pill.dataset.value)) ? "true" : "false");
        });
        resetExamplesAndBrands("Select an attribute to see relevant brands.");
        loadCategories().catch((error) => setError(error.message));
      });
      retailerPills.appendChild(button);
    });
  }

  function renderBrandPills(brands, options = {}) {
    const emptyMessage = options.emptyMessage || "No brands available.";
    brandPills.innerHTML = "";
    if (!brands.length) {
      const empty = document.createElement("span");
      empty.className = "muted";
      empty.textContent = emptyMessage;
      brandPills.appendChild(empty);
      selectedBrands = new Set([ALL_BRANDS_VALUE]);
      return;
    }

    const values = brands.map((item) => String(item.value || item));
    const available = new Set(values);
    const nextSelected = new Set(
      Array.from(selectedBrands).filter((value) => value === ALL_BRANDS_VALUE || available.has(String(value))),
    );
    if (!nextSelected.size) {
      nextSelected.add(ALL_BRANDS_VALUE);
    } else if (Array.from(nextSelected).some((value) => value !== ALL_BRANDS_VALUE)) {
      nextSelected.delete(ALL_BRANDS_VALUE);
    }
    selectedBrands = nextSelected;

    const allButton = document.createElement("button");
    allButton.type = "button";
    allButton.className = "coverage-pill";
    allButton.dataset.value = ALL_BRANDS_VALUE;
    allButton.setAttribute("aria-pressed", selectedBrands.has(ALL_BRANDS_VALUE) ? "true" : "false");
    allButton.textContent = "All";
    allButton.addEventListener("click", () => {
      if (selectedBrands.size === 1 && selectedBrands.has(ALL_BRANDS_VALUE)) {
        return;
      }
      selectedBrands = new Set([ALL_BRANDS_VALUE]);
      Array.from(brandPills.querySelectorAll(".coverage-pill")).forEach((pill) => {
        pill.setAttribute("aria-pressed", pill.dataset.value === ALL_BRANDS_VALUE ? "true" : "false");
      });
      refreshExamplesForSelection();
    });
    brandPills.appendChild(allButton);

    brands.forEach((item) => {
      const value = item.value || item;
      const label = item.label || item;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "coverage-pill";
      button.dataset.value = value;
      button.setAttribute("aria-pressed", selectedBrands.has(String(value)) ? "true" : "false");
      button.textContent = label;
      button.addEventListener("click", () => {
        const valueKey = String(value);
        if (selectedBrands.has(valueKey)) {
          selectedBrands.delete(valueKey);
        } else {
          selectedBrands.add(valueKey);
        }
        if (selectedBrands.size === 0) {
          selectedBrands.add(ALL_BRANDS_VALUE);
        } else {
          selectedBrands.delete(ALL_BRANDS_VALUE);
        }
        Array.from(brandPills.querySelectorAll(".coverage-pill")).forEach((pill) => {
          pill.setAttribute("aria-pressed", selectedBrands.has(String(pill.dataset.value)) ? "true" : "false");
        });
        refreshExamplesForSelection();
      });
      brandPills.appendChild(button);
    });
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

  function renderSummary(totalRecords) {
    summaryCards.innerHTML = "";
    const summaryItems = [{ label: "Records", value: formatNumber(totalRecords) }];
    const card = document.createElement("div");
    card.className = "coverage-mini-card coverage-summary-card";
    card.innerHTML = `
      <h3>Totals</h3>
      <div class="coverage-summary-grid">
        ${summaryItems
          .map(
            (item) => `
          <div class="coverage-summary-item">
            <div class="coverage-summary-label">${item.label}</div>
            <div class="coverage-summary-value">${item.value}</div>
          </div>
        `,
          )
          .join("")}
      </div>
    `;
    summaryCards.appendChild(card);
  }

  function renderCoverageTable(attributes) {
    coverageTableBody.innerHTML = "";
    if (!attributes || !attributes.length) {
      const row = document.createElement("tr");
      row.innerHTML = `<td colspan="5">No coverage data.</td>`;
      coverageTableBody.appendChild(row);
      return;
    }
    const sorted = [...attributes].sort((a, b) => {
      const filledA = Number(a.filled_pct);
      const filledB = Number(b.filled_pct);
      const safeFilledA = Number.isFinite(filledA) ? filledA : 0;
      const safeFilledB = Number.isFinite(filledB) ? filledB : 0;
      if (safeFilledB !== safeFilledA) {
        return safeFilledB - safeFilledA;
      }
      const labelA = String(a.label || "");
      const labelB = String(b.label || "");
      return labelA.localeCompare(labelB, undefined, { sensitivity: "base" });
    });
    for (const attr of sorted) {
      const row = document.createElement("tr");
      const attrId = String(attr.id);
      row.dataset.attrId = attrId;
      row.dataset.attrColumn = attr.column || "";
      row.innerHTML = `
        <td>${attr.label}</td>
        <td>${formatPct(attr.filled_pct)}</td>
        <td>${formatPct(attr.missing_pct)}</td>
        <td>${formatPct(attr.not_in_taxonomy_pct)}</td>
        <td>${formatConfidenceValue(attr)}</td>
      `;
      row.addEventListener("click", () => {
        fetchExamples(attrId, attr.label, attr.column || "");
      });
      if (selectedExampleAttribute && String(selectedExampleAttribute.id) === attrId) {
        row.classList.add("coverage-table-row--selected");
        row.setAttribute("aria-selected", "true");
      }
      coverageTableBody.appendChild(row);
    }
  }

  function setCoverageSelection(attributeId) {
    const selectedId = attributeId ? String(attributeId) : "";
    Array.from(coverageTableBody.querySelectorAll("tr[data-attr-id]")).forEach((row) => {
      const isSelected = selectedId && row.dataset.attrId === selectedId;
      row.classList.toggle("coverage-table-row--selected", isSelected);
      row.setAttribute("aria-selected", isSelected ? "true" : "false");
    });
  }

  function scheduleCoverageLoad() {
    if (coverageLoadTimer) {
      window.clearTimeout(coverageLoadTimer);
    }
    coverageLoadTimer = window.setTimeout(() => {
      loadCoverage().catch((error) => {
        setError(error.message);
        setStatus("");
      });
    }, 300);
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

  async function loadRetailers() {
    const data = await fetchJSON("/retailers");
    renderRetailerPills((data.retailers || []).map((value) => ({ value, label: value })));
    renderBrandPills([], { emptyMessage: "Select an attribute to see relevant brands." });
  }

  async function loadCategories() {
    const retailer = Array.from(selectedRetailers);
    if (!retailer.length) {
      setError("Select at least one retailer first.");
      renderCategoryPills([]);
      return;
    }
    const query = buildQuery({ retailer });
    const data = await fetchJSON(`/categories?${query}`);
    renderCategoryPills(data.categories || []);
  }

  async function loadCoverage() {
    const retailer = Array.from(selectedRetailers);
    const category = selectedCategory;
    const recordType = selectedRecordType;
    if (!retailer.length) {
      setError("Select at least one retailer before loading coverage.");
      return;
    }
    if (!category) {
      setError("Select a category before loading coverage.");
      return;
    }
    setError("");
    setStatus("Loading coverage…");
    const query = buildQuery({
      retailer,
      category: [category],
      record_type: recordType,
    });
    const data = await fetchJSON(`/coverage?${query}`);
    lastCoverage = data;
    renderSummary(data.total_records || 0);
    renderCoverageTable(data.attributes || []);
    examplesContainer.innerHTML = "";
    selectedExampleAttribute = null;
    setCoverageSelection(null);
    renderBrandPills([], { emptyMessage: "Select an attribute to see relevant brands." });
    setStatus("Coverage loaded.");
  }

  async function loadRelevantBrands(attributeId) {
    if (!attributeId) {
      renderBrandPills([], { emptyMessage: "Select an attribute to see relevant brands." });
      return;
    }
    const retailer = Array.from(selectedRetailers);
    if (!retailer.length || !selectedCategory) {
      renderBrandPills([], { emptyMessage: "Select retailers and a category first." });
      return;
    }
    const analysisConfig = getAnalysisConfig();
    const query = buildQuery({
      retailer,
      category: [selectedCategory],
      record_type: selectedRecordType,
      attribute_id: attributeId,
      analysis: selectedAnalysis,
    });
    const data = await fetchJSON(`/brands/relevant?${query}`);
    renderBrandPills((data.brands || []).map((value) => ({ value, label: value })), {
      emptyMessage: analysisConfig.emptyBrands,
    });
  }

  async function fetchTaxonomyBranch(attributeId) {
    if (!attributeId || !selectedCategory) {
      return { nodes: [] };
    }
    const query = buildQuery({
      category: [selectedCategory],
      attribute_id: attributeId,
    });
    return fetchJSON(`/taxonomy/branch?${query}`);
  }

  function refreshBrandsForSelection() {
    if (!selectedExampleAttribute) {
      renderBrandPills([], { emptyMessage: "Select an attribute to see relevant brands." });
      return;
    }
    loadRelevantBrands(selectedExampleAttribute.id).catch((error) => setError(error.message));
  }

  function resetExamplesAndBrands(message) {
    examplesContainer.innerHTML = "";
    selectedExampleAttribute = null;
    setCoverageSelection(null);
    renderBrandPills([], { emptyMessage: message || "Select an attribute to see relevant brands." });
  }

  async function fetchExamples(attributeId, attributeLabel, attributeColumn) {
    if (!attributeId) {
      return;
    }
    if (!selectedCategory) {
      return;
    }
    const analysisConfig = getAnalysisConfig();
    setStatus(`Loading ${analysisConfig.label} examples for ${attributeLabel}…`);
    selectedExampleAttribute = { id: attributeId, label: attributeLabel, column: attributeColumn };
    setCoverageSelection(attributeId);
    loadRelevantBrands(attributeId).catch((error) => setError(error.message));
    const retailer = Array.from(selectedRetailers);
    const brands = Array.from(selectedBrands).filter((brand) => brand !== ALL_BRANDS_VALUE);
    const category = selectedCategory;
    const recordType = selectedRecordType;
    const filters = [`${attributeId}:${analysisConfig.filterValue}`];
    const query = buildQuery({
      retailer,
      brand: brands,
      category: [category],
      record_type: recordType,
      filters,
      audit_attribute_id:
        selectedAnalysis === "found" || selectedAnalysis === "not_in_taxonomy"
          ? attributeId
          : "",
      limit: "12",
    });
    try {
      const [recordsResult, taxonomyResult] = await Promise.allSettled([
        fetchJSON(`/records?${query}`),
        fetchTaxonomyBranch(attributeId),
      ]);
      const records =
        recordsResult.status === "fulfilled" ? recordsResult.value.records || [] : [];
      const taxonomyNodes =
        taxonomyResult.status === "fulfilled" ? taxonomyResult.value.nodes || [] : [];
      let taxonomyError = null;
      if (recordsResult.status === "rejected") {
        setError(recordsResult.reason?.message || "Failed to load examples.");
      }
      if (taxonomyResult.status === "rejected") {
        taxonomyError = `Unable to load taxonomy values: ${parseErrorMessage(taxonomyResult.reason)}`;
        setError(taxonomyError);
      }
      renderExamples(attributeLabel, records, taxonomyNodes, taxonomyError, {
        analysis: selectedAnalysis,
        column: attributeColumn,
      });
      setStatus(`Loaded ${records.length} examples.`);
    } catch (error) {
      setError(error.message);
      setStatus("");
    }
  }

  function refreshExamplesForSelection() {
    if (!selectedExampleAttribute) {
      return;
    }
    fetchExamples(
      selectedExampleAttribute.id,
      selectedExampleAttribute.label,
      selectedExampleAttribute.column || "",
    ).catch((error) => {
      setError(error.message);
      setStatus("");
    });
  }

  function renderTaxonomyBranch(attributeLabel, nodes, error) {
    const taxonomyCard = document.createElement("div");
    taxonomyCard.className = "coverage-mini-card coverage-mini-card--taxonomy";
    taxonomyCard.innerHTML = `<h3>${attributeLabel} taxonomy values</h3>`;
    const taxonomyList = document.createElement("div");
    taxonomyList.className = "coverage-taxonomy-list";
    const filteredNodes = nodes.filter((node) => !isExcludedTaxonomyNode(node));
    if (error) {
      const errorRow = document.createElement("div");
      errorRow.className = "coverage-empty";
      errorRow.textContent = error;
      taxonomyList.appendChild(errorRow);
    } else if (!filteredNodes.length) {
      const empty = document.createElement("div");
      empty.className = "coverage-empty";
      empty.textContent = "No taxonomy values found for this attribute.";
      taxonomyList.appendChild(empty);
    } else {
      filteredNodes.forEach((node) => {
        const row = document.createElement("div");
        row.className = "coverage-taxonomy-row";
        row.style.paddingLeft = `${node.depth * 16}px`;
        const label = document.createElement("div");
        label.className = "coverage-taxonomy-label";
        label.textContent = node.label;
        row.appendChild(label);
        if (node.synonyms && node.synonyms.length) {
          const synonyms = document.createElement("div");
          synonyms.className = "coverage-taxonomy-synonyms";
          synonyms.textContent = `Synonyms: ${node.synonyms.join(", ")}`;
          row.appendChild(synonyms);
        }
        taxonomyList.appendChild(row);
      });
    }
    taxonomyCard.appendChild(taxonomyList);
    examplesContainer.appendChild(taxonomyCard);
  }

  function renderExamples(attributeLabel, records, taxonomyNodes, taxonomyError, options = {}) {
    examplesContainer.innerHTML = "";
    const safeNodes = Array.isArray(taxonomyNodes) ? taxonomyNodes : [];
    renderTaxonomyBranch(attributeLabel, safeNodes, taxonomyError);
    const deterministicResults = computeDeterministicMatches(records, safeNodes);
    renderDeterministicSummary(deterministicResults);
    if (!records.length) {
      const empty = document.createElement("div");
      empty.className = "coverage-empty";
      empty.textContent = "No examples found for this attribute.";
      examplesContainer.appendChild(empty);
      return;
    }

    const analysisMode = options.analysis || "na";
    const attributeColumn = options.column || "";

    records.forEach((record, index) => {
      const card = document.createElement("div");
      card.className = "coverage-mini-card";
      const brand = record.brand || "Unknown brand";
      const name = record.product_name || record.product || "Unknown product";
      card.innerHTML = `
        <div><strong>${brand}</strong></div>
        <div class="coverage-example-image-wrapper"></div>
        <div class="coverage-example-name"></div>
      `;
      const imageWrapper = card.querySelector(".coverage-example-image-wrapper");
      const hero = sanitizeUrl(record.hero_image_url);
      const swatch = sanitizeUrl(record.swatch_image_url);
      const parentId = record.parent_product_id || record.product || record.parent;
      const variantId = record.variant_id || record.variant;
      let imgUrl = hero || swatch;
      if (!imgUrl && parentId) {
        const params = new URLSearchParams();
        if (variantId) params.append("variant", variantId);
        imgUrl = `${apiBase}/images/${parentId}${params.toString() ? "?" + params.toString() : ""}`;
      }
      if (imgUrl) {
        const image = document.createElement("img");
        image.src = imgUrl;
        image.alt = "";
        image.className = "coverage-example-image";
        imageWrapper.appendChild(image);
      }
      const nameContainer = card.querySelector(".coverage-example-name");
      const pdpUrl = typeof record.pdp_url === "string" ? record.pdp_url.trim() : "";
      if (pdpUrl) {
        const link = document.createElement("a");
        link.href = pdpUrl;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = name;
        link.style.color = "inherit";
        link.style.textDecoration = "underline";
        nameContainer.appendChild(link);
      } else {
        nameContainer.textContent = name;
      }
      const pdpText =
        record.pdp_text ||
        record.product_description ||
        record.description_markdown ||
        record.description ||
        record.variant_description ||
        "No PDP text available.";
      const pdpBody = document.createElement("div");
      pdpBody.className = "coverage-example-text";
      const recordId =
        record.parent_product_id || record.product || record.parent || String(index);
      const matchedTerms = deterministicResults.recordMatchMap.get(recordId);
      pdpBody.innerHTML = highlightMatchedTerms(pdpText, matchedTerms);
      card.appendChild(pdpBody);
      if (analysisMode === "found" || analysisMode === "not_in_taxonomy") {
        const valueContainer = document.createElement("div");
        valueContainer.className = "coverage-example-meta";
        const valueLabel = document.createElement("div");
        valueLabel.className = "coverage-example-label";
        valueLabel.textContent =
          analysisMode === "not_in_taxonomy"
            ? "Not in taxonomy value"
            : "Selected value";
        const valueText = document.createElement("div");
        valueText.className = "coverage-example-text";
        if (analysisMode === "not_in_taxonomy") {
          const detail = extractNotInTaxonomyExampleValue(record, attributeColumn);
          valueText.textContent = detail || "N/A";
        } else {
          const rawValue = attributeColumn ? record[attributeColumn] : null;
          valueText.textContent = rawValue ? String(rawValue) : "N/A";
        }
        valueContainer.appendChild(valueLabel);
        valueContainer.appendChild(valueText);
        card.appendChild(valueContainer);

        if (analysisMode === "found") {
          const auditBlock = document.createElement("div");
          auditBlock.className = "coverage-example-audit";
          const audit = record.attribute_audit;
          if (!audit) {
            auditBlock.textContent = "Audit unavailable.";
          } else {
            const source = audit.source || "unknown";
            const rule = audit.decision_rule || "unknown";
            const evidence = audit.evidence || {};
            const addAuditLine = (label, value, options = {}) => {
              const row = document.createElement("div");
              if (options.asLink) {
                row.appendChild(document.createTextNode(`${label}: `));
                const link = document.createElement("a");
                link.href = value;
                link.target = "_blank";
                link.rel = "noopener noreferrer";
                link.textContent = value;
                link.style.color = "inherit";
                link.style.textDecoration = "underline";
                row.appendChild(link);
              } else {
                row.textContent = `${label}: ${value}`;
              }
              auditBlock.appendChild(row);
            };
            const usedKeys = new Set();
            addAuditLine("Source", source);
            addAuditLine("Decision", rule);
            if (audit.promoted !== undefined && audit.promoted !== null) {
              addAuditLine("Promoted", audit.promoted ? "yes" : "no");
            }
            const supportRunsRaw = Number(audit.support_runs);
            const totalRunsRaw = Number(audit.total_runs);
            if (
              Number.isFinite(supportRunsRaw) &&
              Number.isFinite(totalRunsRaw) &&
              totalRunsRaw > 0
            ) {
              const supportRuns = Math.max(0, Math.trunc(supportRunsRaw));
              const totalRuns = Math.max(0, Math.trunc(totalRunsRaw));
              const availableRunsRaw = Number(audit.available_runs);
              const availableRuns =
                Number.isFinite(availableRunsRaw) && availableRunsRaw > 0
                  ? Math.max(0, Math.trunc(availableRunsRaw))
                  : totalRuns;
              const displayTotalRuns = Math.max(totalRuns, availableRuns);
              const displayAgreementRate = supportRuns / displayTotalRuns;
              let confirmedText = `${supportRuns}/${displayTotalRuns}`;
              confirmedText += ` (${(displayAgreementRate * 100).toFixed(0)}%)`;
              addAuditLine("Confirmed", confirmedText);
            }
            if (evidence.confidence !== undefined && evidence.confidence !== null) {
              addAuditLine("Confidence", evidence.confidence);
              usedKeys.add("confidence");
            }
            if (evidence.image_source) {
              addAuditLine("Image source", evidence.image_source);
              usedKeys.add("image_source");
            }
            if (evidence.image_path) {
              addAuditLine("Image path", evidence.image_path);
              usedKeys.add("image_path");
            }
            if (evidence.hero_image_url) {
              const heroImageUrl = sanitizeUrl(evidence.hero_image_url) || evidence.hero_image_url;
              addAuditLine("Image URL", heroImageUrl, {
                asLink: isHttpUrl(heroImageUrl),
              });
              usedKeys.add("hero_image_url");
            }
            if (evidence.evidence_url) {
              const evidenceUrl = sanitizeUrl(evidence.evidence_url) || evidence.evidence_url;
              addAuditLine("Evidence URL", evidenceUrl, {
                asLink: isHttpUrl(evidenceUrl),
              });
              usedKeys.add("evidence_url");
            }
            Object.entries(evidence).forEach(([key, value]) => {
              if (usedKeys.has(key)) {
                return;
              }
              if (key === "stage_source") {
                return;
              }
              if (value === null || value === undefined || value === "") {
                return;
              }
              addAuditLine(key, value);
            });
          }
          card.appendChild(auditBlock);
        }
      }
      examplesContainer.appendChild(card);
    });
  }

  function wireViewToggle() {
    const currentPath = window.location.pathname;
    viewButtons.forEach((button) => {
      const target = button.dataset.reviewView;
      if (!target) {
        return;
      }
      const isActive = currentPath === target;
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
      button.disabled = isActive;
      if (!isActive) {
        button.addEventListener("click", () => {
          window.location.href = target;
        });
      }
    });
  }

  const recordTypeOptions = [
    { value: "parent", label: "Parent" },
    { value: "variant", label: "Variant" },
  ];

  loadRetailers()
    .then(loadCategories)
    .catch((error) => setError(error.message));

  renderRecordTypePills(recordTypeOptions);
  wireAnalysisPills();

  wireViewToggle();
})();

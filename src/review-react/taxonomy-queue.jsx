import React, { useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom";

const taxonomyBase = `${window.location.origin.replace(/\/$/, "")}/review/taxonomy`;
const apiBase = `${window.location.origin.replace(/\/$/, "")}/review`;
const supportedIssueTypes = new Set([
  "same_term_same_attribute_collision",
  "cross_retailer_assignment_inconsistency",
]);

const panelStyle = {
  border: "1px solid #e5e7eb",
  borderRadius: 12,
  padding: 12,
  background: "#fff",
  marginBottom: 12,
};

const inputStyle = {
  width: "100%",
  border: "1px solid #d1d5db",
  borderRadius: 10,
  padding: "8px 10px",
  fontSize: 13,
  background: "#fff",
};

const buttonStyle = {
  border: "1px solid #e5e7eb",
  borderRadius: 999,
  padding: "6px 10px",
  background: "#fff",
  color: "#111827",
  cursor: "pointer",
  fontSize: 13,
};

const primaryButtonStyle = {
  border: "1px solid #111827",
  borderRadius: 999,
  padding: "6px 10px",
  background: "#111827",
  color: "#fff",
  cursor: "pointer",
  fontSize: 13,
};

function sanitizeUrl(url) {
  if (!url) return "";
  let cleaned = String(url).trim();
  cleaned = cleaned.replace(/\\u002F/gi, "/").replace(/\\\//g, "/");
  return cleaned || "";
}

function isHttpUrl(url) {
  try {
    const parsed = new URL(String(url || ""));
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch (err) {
    return false;
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch (err) {
    payload = null;
  }
  if (!response.ok) {
    const detail = payload && payload.detail ? payload.detail : `Request failed (${response.status})`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

function SegmentedButton({ label, active, onClick, tooltip }) {
  const [hover, setHover] = useState(false);
  return (
    <span style={{ position: "relative", display: "inline-block" }}>
      <button
        type="button"
        aria-pressed={active}
        onClick={active ? undefined : onClick}
        style={{
          border: "1px solid #e5e7eb",
          borderRadius: 999,
          padding: "6px 10px",
          background: active ? "#111827" : "#fff",
          color: active ? "#fff" : "#111827",
          cursor: active ? "default" : "pointer",
          fontSize: 13,
        }}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
      >
        {label}
      </button>
      {hover && tooltip ? (
        <span
          role="tooltip"
          style={{
            position: "absolute",
            bottom: "100%",
            left: "50%",
            transform: "translateX(-50%)",
            marginBottom: 6,
            padding: "6px 8px",
            background: "#111827",
            color: "#fff",
            borderRadius: 6,
            fontSize: 12,
            whiteSpace: "nowrap",
            zIndex: 10,
            boxShadow: "0 6px 16px rgba(0,0,0,0.15)",
          }}
        >
          {tooltip}
        </span>
      ) : null}
    </span>
  );
}

function ViewToggle({ active = "taxonomy" }) {
  return (
    <div style={{ display: "inline-flex", gap: 8, flexWrap: "wrap" }}>
      <SegmentedButton label="Catalog" active={active === "catalog"} onClick={() => { if (active !== "catalog") window.location.href = "/review/page"; }} tooltip="See filtered products" />
      <SegmentedButton label="Coverage" active={active === "coverage"} onClick={() => { if (active !== "coverage") window.location.href = "/review/coverage/page"; }} tooltip="Explore attribute coverage and evidence" />
      <SegmentedButton label="Explicit attributes" active={active === "explicit"} onClick={() => { if (active !== "explicit") window.location.href = "/review/explicit-rules/page"; }} tooltip="Review explicit attributes" />
      <SegmentedButton label="Issues" active={active === "taxonomy"} onClick={() => { if (active !== "taxonomy") window.location.href = "/review/issues/page"; }} tooltip="Review automatically surfaced attribute issues" />
    </div>
  );
}

function issueTypeLabel(type) {
  return {
    same_term_same_attribute_collision: "Same term collision",
    cross_retailer_assignment_inconsistency: "Same product, different value",
  }[String(type || "")] || String(type || "Unknown issue");
}

function badge(label, palette) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", borderRadius: 999, padding: "2px 10px", background: palette.bg, color: palette.fg, fontSize: 12, fontWeight: 600 }}>
      {label}
    </span>
  );
}

function issueTypeBadge(type) {
  const palette = {
    same_term_same_attribute_collision: { bg: "#ede9fe", fg: "#5b21b6" },
    cross_retailer_assignment_inconsistency: { bg: "#fee2e2", fg: "#991b1b" },
  }[String(type || "")] || { bg: "#f3f4f6", fg: "#374151" };
  return badge(issueTypeLabel(type), palette);
}

function isCrossRetailerIssue(candidateType) {
  return String(candidateType || "") === "cross_retailer_assignment_inconsistency";
}

function displayIssueTitle(item) {
  const title = String(item?.title || "").trim();
  if (!isCrossRetailerIssue(item?.candidate_type)) return title;
  const match = title.match(/^Cross-retailer inconsistency in\s+(.+?)\s*:\s*(.+)$/i);
  if (!match) return title;
  const values = match[2];
  const attributeLabel = String(item?.attribute_label || item?.attribute_id || "").trim();
  return attributeLabel ? `${attributeLabel}: ${values}` : title;
}

function displayDetailTitle(detail) {
  if (!isCrossRetailerIssue(detail?.item?.candidate_type)) {
    return displayIssueTitle(detail?.item);
  }
  const title = String(detail?.item?.title || "").trim();
  const match = title.match(/^Cross-retailer inconsistency in\s+(.+?)\s*:\s*(.+)$/i);
  if (!match) return title;
  const values = match[2];
  const attributeLabel = String(
    detail?.taxonomy_context?.attribute_label
    || detail?.taxonomy_context?.attribute_id
    || detail?.item?.attribute_id
    || ""
  ).trim();
  return attributeLabel ? `${attributeLabel}: ${values}` : displayIssueTitle(detail?.item);
}

function formatList(values) {
  return Array.isArray(values) && values.length ? values.join(", ") : "-";
}

function formatAuditSource(audit) {
  const source = String(audit?.source || "").trim();
  if (!source) return "Not recorded";
  if (source === "llm") return "LLM";
  if (source === "deterministic") return "Deterministic";
  if (source === "deterministic_explicit") return "Explicit";
  if (source === "explicit") return "Explicit";
  return source;
}

function resolveIssueImage(entry) {
  const hero = sanitizeUrl(entry?.hero_image_url);
  const swatch = sanitizeUrl(entry?.swatch_image_url);
  if (hero) return hero;
  if (swatch) return swatch;
  const parentId = String(entry?.parent_product_id || "").trim();
  const variantId = String(entry?.variant_id || "").trim();
  if (!parentId) return "";
  const params = new URLSearchParams();
  if (variantId) params.append("variant", variantId);
  return `${apiBase}/images/${parentId}${params.toString() ? `?${params.toString()}` : ""}`;
}

function issuePdpText(entry) {
  const fields = [
    entry?.pdp_text,
    entry?.product_description,
    entry?.description_markdown,
    entry?.description,
    entry?.variant_description,
  ];
  const text = fields.find((value) => String(value || "").trim());
  return String(text || "No PDP text available.").trim();
}

function compactText(value) {
  return String(value || "").trim();
}

function humanizeToken(value) {
  const text = compactText(value).replace(/_/g, " ");
  if (!text) return "";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function formatSourceLabel(source) {
  const text = compactText(source).toLowerCase();
  if (!text) return "";
  if (text === "llm") return "LLM";
  if (text === "deterministic") return "Deterministic";
  if (text === "deterministic_explicit") return "Explicit";
  if (text === "explicit") return "Explicit";
  return humanizeToken(text);
}

function supportingSourceLabels(audit) {
  const raw = Array.isArray(audit?.supporting_sources) ? audit.supporting_sources : [];
  return raw.map((item) => formatSourceLabel(item)).filter(Boolean);
}

function supportStrengthLabel(audit) {
  const supportRuns = Number(audit?.support_runs);
  const totalRuns = Number(audit?.total_runs);
  if (Number.isFinite(supportRuns) && Number.isFinite(totalRuns) && totalRuns > 1) {
    return `Confirmed ${supportRuns}/${totalRuns}`;
  }
  return "";
}

function auditScore(audit) {
  if (!audit) return 0;
  const promoted = audit?.promoted ? 1 : 0;
  const agreementRate = Number.isFinite(Number(audit?.agreement_rate)) ? Number(audit.agreement_rate) : 0;
  const supportRuns = Number.isFinite(Number(audit?.support_runs)) ? Number(audit.support_runs) : 0;
  return promoted * 100 + agreementRate * 10 + supportRuns;
}

function groupVerdict(cards) {
  if (!Array.isArray(cards) || cards.length < 2) return "";
  const ranked = [...cards]
    .map((entry) => ({
      retailer: compactText(entry?.retailer) || "Unknown retailer",
      audit: entry?.attribute_audit || null,
      score: auditScore(entry?.attribute_audit || null),
    }))
    .sort((left, right) => right.score - left.score);
  const [first, second] = ranked;
  if (!first || !second) return "";
  const firstPromoted = Boolean(first.audit?.promoted);
  const secondPromoted = Boolean(second.audit?.promoted);
  const firstAgreement = Number.isFinite(Number(first.audit?.agreement_rate)) ? Number(first.audit.agreement_rate) : 0;
  const secondAgreement = Number.isFinite(Number(second.audit?.agreement_rate)) ? Number(second.audit.agreement_rate) : 0;
  const firstSupport = Number.isFinite(Number(first.audit?.support_runs)) ? Number(first.audit.support_runs) : 0;
  const secondSupport = Number.isFinite(Number(second.audit?.support_runs)) ? Number(second.audit.support_runs) : 0;
  if (firstPromoted && !secondPromoted) return `Stronger support: ${first.retailer}`;
  if (firstAgreement - secondAgreement >= 0.25) return `Stronger support: ${first.retailer}`;
  if (firstSupport - secondSupport >= 2) return `Stronger support: ${first.retailer}`;
  return "No clear stronger side from the recorded history.";
}

function pairSummaryLine(cards) {
  return (Array.isArray(cards) ? cards : []).map((entry) => {
    const retailer = compactText(entry?.retailer) || "Unknown retailer";
    const value = compactText(entry?.value_id) || "N/A";
    const chosenBy = formatAuditSource(entry?.attribute_audit);
    const support = supportStrengthLabel(entry?.attribute_audit);
    if (chosenBy && support) return `${retailer}: ${value} via ${chosenBy}, ${support}`;
    if (chosenBy) return `${retailer}: ${value} via ${chosenBy}`;
    if (support) return `${retailer}: ${value}, ${support}`;
    return `${retailer}: ${value}`;
  }).join(" | ");
}

function keyEvidenceSnippet(entry) {
  const note = compactText(entry?.attribute_audit?.evidence?.note);
  if (note) return note;
  const fullText = issuePdpText(entry);
  if (!fullText || fullText === "No PDP text available.") return fullText;
  const firstParagraph = fullText.split(/\n\s*\n/).find((part) => compactText(part)) || fullText;
  const normalized = firstParagraph.replace(/\s+/g, " ").trim();
  if (normalized.length <= 320) return normalized;
  const clipped = normalized.slice(0, 320);
  const boundary = clipped.lastIndexOf(" ");
  return `${(boundary > 80 ? clipped.slice(0, boundary) : clipped).trim()}...`;
}

function fullPdpTextAvailable(entry) {
  const fullText = issuePdpText(entry);
  return fullText && fullText !== "No PDP text available.";
}

function CrossRetailerCard({ entry, cardIndex }) {
  const brand = String(entry?.brand || "").trim() || "Unknown brand";
  const name = String(entry?.product_name || entry?.display_name || "").trim() || "Unknown product";
  const retailer = String(entry?.retailer || "").trim() || "Unknown retailer";
  const pdpUrl = sanitizeUrl(entry?.pdp_url);
  const imageUrl = resolveIssueImage(entry);
  const audit = entry?.attribute_audit || null;
  const evidenceUrl = sanitizeUrl(audit?.evidence?.evidence_url);
  const supportingSources = supportingSourceLabels(audit);
  const snippet = keyEvidenceSnippet(entry);
  const support = supportStrengthLabel(audit);

  return (
    <div
      key={`${retailer}-${entry?.parent_product_id || cardIndex}`}
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: 12,
        padding: 12,
        background: "#fff",
        display: "flex",
        flexDirection: "column",
        gap: 10,
        alignItems: "stretch",
        justifyContent: "flex-start",
      }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ display: "inline-flex", alignItems: "center", borderRadius: 999, padding: "2px 10px", background: "#eef2ff", color: "#3730a3", fontSize: 12, fontWeight: 600 }}>
          {retailer}
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", borderRadius: 999, padding: "2px 10px", background: "#f3f4f6", color: "#111827", fontSize: 12, fontWeight: 600 }}>
          {entry?.value_id || "N/A"}
        </span>
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        <span style={{ display: "inline-flex", alignItems: "center", borderRadius: 999, padding: "2px 10px", background: "#f9fafb", color: "#111827", fontSize: 12, fontWeight: 600 }}>
          Source: {formatAuditSource(audit)}
        </span>
        {support ? (
          <span style={{ display: "inline-flex", alignItems: "center", borderRadius: 999, padding: "2px 10px", background: "#f9fafb", color: "#111827", fontSize: 12, fontWeight: 600 }}>
            {support}
          </span>
        ) : null}
        {supportingSources.length ? (
          <span style={{ display: "inline-flex", alignItems: "center", borderRadius: 999, padding: "2px 10px", background: "#f9fafb", color: "#111827", fontSize: 12, fontWeight: 600 }}>
            Supporting sources: {supportingSources.join(", ")}
          </span>
        ) : null}
      </div>

      <div style={{ fontSize: 13, fontWeight: 700, color: "#111827" }}>{brand}</div>

      <div style={{ width: "100%", minHeight: 140, borderRadius: 10, overflow: "hidden", background: "#f9fafb", border: "1px solid #f3f4f6", display: "flex", alignItems: "center", justifyContent: "center" }}>
        {imageUrl ? (
          <img src={imageUrl} alt="" style={{ width: "100%", height: 220, objectFit: "contain", display: "block", background: "#fff" }} />
        ) : (
          <div style={{ fontSize: 12, color: "#9ca3af" }}>No image</div>
        )}
      </div>

      <div style={{ fontSize: 14, fontWeight: 600, color: "#111827", lineHeight: 1.4 }}>
        {pdpUrl ? (
          <a href={pdpUrl} target="_blank" rel="noopener noreferrer" style={{ color: "inherit", textDecoration: "underline" }}>
            {name}
          </a>
        ) : (
          name
        )}
      </div>

      <div style={{ display: "grid", gap: 6 }}>
        <div style={{ fontSize: 12, color: "#374151", whiteSpace: "pre-wrap", lineHeight: 1.45 }}>
          {snippet}
        </div>
        {evidenceUrl && isHttpUrl(evidenceUrl) ? (
          <div style={{ fontSize: 12 }}>
            <a href={evidenceUrl} target="_blank" rel="noopener noreferrer">
              Evidence link
            </a>
          </div>
        ) : null}
        {fullPdpTextAvailable(entry) && snippet !== issuePdpText(entry) ? (
          <details>
            <summary style={{ cursor: "pointer", fontSize: 12, color: "#374151" }}>Show full PDP text</summary>
            <div style={{ marginTop: 8, fontSize: 12, color: "#374151", whiteSpace: "pre-wrap", lineHeight: 1.45 }}>
              {issuePdpText(entry)}
            </div>
          </details>
        ) : null}
      </div>
    </div>
  );
}

function renderCrossRetailerGroups(detail) {
  const groups = Array.isArray(detail?.diagnostic_groups) ? detail.diagnostic_groups : [];
  if (!groups.length) {
    return <div style={{ fontSize: 13, color: "#6b7280" }}>No comparison cards available for this issue yet.</div>;
  }
  return (
    <div style={{ display: "grid", gap: 12 }}>
      {groups.map((group, groupIndex) => (
        <div key={`group-${groupIndex}`} style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 12, background: "#fff" }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: "#111827", marginBottom: 10 }}>
            {group.group_label || `Product group ${groupIndex + 1}`}
          </div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 10 }}>
            <div style={{ fontSize: 12, color: "#6b7280" }}>
              <strong style={{ color: "#374151" }}>Category:</strong>{" "}
              {(detail?.taxonomy_context?.category_label
                || detail?.taxonomy_context?.category_key
                || group.category_key
                || detail?.item?.category_key
                || "-")}
            </div>
            <div style={{ fontSize: 12, color: "#6b7280" }}>
              <strong style={{ color: "#374151" }}>Attribute:</strong>{" "}
              {(detail?.taxonomy_context?.attribute_label
                || detail?.taxonomy_context?.attribute_id
                || group.attribute_id
                || detail?.item?.attribute_id
                || "-")}
            </div>
          </div>
          <div style={{ display: "grid", gap: 4, marginBottom: 10 }}>
            <div style={{ fontSize: 12, color: "#374151" }}>{pairSummaryLine(group.cards || [])}</div>
            <div style={{ fontSize: 12, color: "#6b7280" }}>{groupVerdict(group.cards || [])}</div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 }}>
            {(group.cards || []).map((entry, cardIndex) => (
              <CrossRetailerCard
                key={`${entry.retailer || "retailer"}-${entry.parent_product_id || cardIndex}`}
                entry={entry}
                cardIndex={cardIndex}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
function renderEvidence(detail) {
  const aggregated = detail?.aggregated || {};
  const summary = aggregated.evidence_summary_json || {};
  if (detail?.item?.candidate_type === "same_term_same_attribute_collision") {
    return (
      <div style={{ display: "grid", gap: 8 }}>
        <div style={{ fontSize: 13, color: "#111827" }}><strong>Term</strong>: {summary.term || aggregated.term || "-"}</div>
        <div style={{ fontSize: 13, color: "#111827" }}><strong>Affected values</strong>: {formatList(summary.affected_value_ids || aggregated.affected_value_ids_json)}</div>
        {(summary.occurrences || []).length ? (
          <div style={{ display: "grid", gap: 6 }}>
            {(summary.occurrences || []).map((occurrence, index) => (
              <div key={`occurrence-${index}`} style={{ borderBottom: "1px solid #f3f4f6", paddingBottom: 6 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#111827" }}>{occurrence.value_id}</div>
                <div style={{ fontSize: 12, color: "#6b7280" }}>{occurrence.role}: {occurrence.text}</div>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    );
  }
  if (detail?.item?.candidate_type === "cross_retailer_assignment_inconsistency") {
    return null;
  }
  return (
    <pre style={{ margin: 0, fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-word", color: "#111827" }}>
      {JSON.stringify(aggregated, null, 2)}
    </pre>
  );
}

function App() {
  const [issues, setIssues] = useState([]);
  const [allIssues, setAllIssues] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({ issueType: "all" });

  const fetchIssues = async () => {
    const taxonomy = await fetchJson(`${taxonomyBase}/queue/items?status=open`);
    const merged = [...(Array.isArray(taxonomy.items) ? taxonomy.items : [])]
      .filter((item) => supportedIssueTypes.has(String(item.candidate_type || "")))
      .sort((left, right) => {
        const leftPriority = Number(left.priority_score || 0);
        const rightPriority = Number(right.priority_score || 0);
        if (rightPriority !== leftPriority) return rightPriority - leftPriority;
        return String(left.title || "").localeCompare(String(right.title || ""));
      });
    setAllIssues(merged);
    const filtered = merged.filter((item) => filters.issueType === "all" || String(item.candidate_type || "") === filters.issueType);
    setIssues(filtered);
    if (filtered.length) {
      setSelectedId((current) => (current && filtered.some((item) => item.queue_item_id === current) ? current : filtered[0].queue_item_id));
    } else {
      setSelectedId("");
      setDetail(null);
    }
  };

  const fetchDetail = async (queueItemId, issueList = issues) => {
    if (!queueItemId) {
      setDetail(null);
      return;
    }
    const selected = issueList.find((item) => item.queue_item_id === queueItemId);
    if (!selected) {
      setDetail(null);
      return;
    }
    const payload = await fetchJson(`${taxonomyBase}/queue/items/${queueItemId}`);
    setDetail(payload);
  };

  useEffect(() => {
    if (!selectedId) return;
    fetchDetail(selectedId).catch((err) => setError(String(err.message || err)));
  }, [selectedId]);

  useEffect(() => {
    const loadIssues = async () => {
      setBusy(true);
      setError("");
      try {
        await fetchJson(`${taxonomyBase}/queue/run`, { method: "POST" });
        await fetchIssues();
      } catch (err) {
        setError(String(err.message || err));
      } finally {
        setBusy(false);
      }
    };
    loadIssues().catch((err) => setError(String(err.message || err)));
  }, [filters.issueType]);

  const issueTypeOptions = useMemo(() => {
    const values = Array.from(new Set(allIssues.map((item) => String(item.candidate_type || "")).filter(Boolean)));
    values.sort((left, right) => issueTypeLabel(left).localeCompare(issueTypeLabel(right)));
    return values;
  }, [allIssues]);

  return (
    <div>
      {error ? <section style={{ ...panelStyle, borderColor: "#fecaca", background: "#fef2f2", color: "#991b1b" }}>{error}</section> : null}

      <section style={panelStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <select value={filters.issueType} onChange={(event) => setFilters({ issueType: event.target.value })} style={{ ...inputStyle, width: 240 }} data-native-select="true" disabled={busy}>
            <option value="all">All issue types</option>
            {issueTypeOptions.map((type) => <option key={type} value={type}>{issueTypeLabel(type)}</option>)}
          </select>
          <ViewToggle active="taxonomy" />
        </div>
        {busy ? <div style={{ marginTop: 10, fontSize: 12, color: "#6b7280" }}>Updating issues…</div> : null}
      </section>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(320px, 420px) minmax(0, 1fr)", gap: 12, alignItems: "start" }}>
        <section style={panelStyle}>
          <div style={{ display: "grid", gap: 8 }}>
            {issues.length ? issues.map((item) => (
              <button key={item.queue_item_id} type="button" onClick={() => setSelectedId(item.queue_item_id)} style={{ border: selectedId === item.queue_item_id ? "1px solid #111827" : "1px solid #e5e7eb", borderRadius: 12, padding: 10, background: "#fff", textAlign: "left", cursor: "pointer" }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", marginBottom: 4 }}>{displayIssueTitle(item)}</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 4 }}>
                  {issueTypeBadge(item.candidate_type)}
                </div>
                <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>
                  <strong style={{ color: "#374151" }}>Category:</strong> {item.category_label || item.category_key || "-"} · <strong style={{ color: "#374151" }}>Attribute:</strong> {item.attribute_label || item.attribute_id || "-"}
                </div>
                {!isCrossRetailerIssue(item.candidate_type) && item.short_reason ? (
                  <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>{item.short_reason}</div>
                ) : null}
                <div style={{ fontSize: 12, color: "#374151" }}>Support: {item.support_product_count ?? 0} products · {item.support_retailer_count ?? 0} retailers</div>
              </button>
            )) : <div style={{ color: "#6b7280", fontSize: 13 }}>No supported issues surfaced yet.</div>}
          </div>
        </section>

        <section style={panelStyle}>
          {!detail ? (
            <div style={{ color: "#6b7280", fontSize: 13 }}>Select an issue.</div>
          ) : (
            <div style={{ display: "grid", gap: 12 }}>
              {isCrossRetailerIssue(detail.item.candidate_type) ? (
                <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                  {issueTypeBadge(detail.item.candidate_type)}
                </div>
              ) : (
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                  <div>
                    <div style={{ fontSize: 18, fontWeight: 600, color: "#111827" }}>{displayDetailTitle(detail)}</div>
                    {detail.item.short_reason ? (
                      <div style={{ fontSize: 12, color: "#6b7280" }}>{detail.item.short_reason}</div>
                    ) : null}
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                    {issueTypeBadge(detail.item.candidate_type)}
                  </div>
                </div>
              )}

              {detail.item.candidate_type !== "cross_retailer_assignment_inconsistency" ? (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 8 }}>
                  <div style={panelStyle}><div style={{ fontSize: 12, color: "#6b7280" }}>Support</div><div style={{ fontSize: 13, color: "#111827" }}>{detail.item.support_product_count ?? 0} products · {detail.item.support_retailer_count ?? 0} retailers</div></div>
                </div>
              ) : null}

              {detail.item.candidate_type === "cross_retailer_assignment_inconsistency" ? (
                <div style={{ display: "grid", gap: 12 }}>
                  {renderCrossRetailerGroups(detail)}
                </div>
              ) : null}

              <div style={panelStyle}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", marginBottom: 6 }}>Current taxonomy context</div>
                <div style={{ fontSize: 13, color: "#111827", marginBottom: 6 }}>{detail.taxonomy_context?.category_label || detail.taxonomy_context?.category_key || detail.item.category_key} / {detail.taxonomy_context?.attribute_label || detail.taxonomy_context?.attribute_id || detail.item.attribute_id}</div>
                {detail.taxonomy_context?.error ? (
                  <div style={{ fontSize: 12, color: "#991b1b", marginBottom: 8 }}>
                    Taxonomy context unavailable: {detail.taxonomy_context.error}
                  </div>
                ) : null}
                <div style={{ display: "grid", gap: 6 }}>
                  {(detail.taxonomy_context?.values || []).map((value) => (
                    <div key={value.value_id} style={{ borderBottom: "1px solid #f3f4f6", paddingBottom: 6 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "#111827" }}>{value.label || value.value_id}</div>
                      <div style={{ fontSize: 12, color: "#6b7280" }}>Synonyms: {formatList(value.synonyms)}</div>
                    </div>
                  ))}
                </div>
              </div>

              {detail.item.candidate_type !== "cross_retailer_assignment_inconsistency" ? (
                <div style={panelStyle}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", marginBottom: 6 }}>Evidence</div>
                  {renderEvidence(detail)}
                </div>
              ) : null}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

const rootNode = document.getElementById("reactTaxonomyQueueApp");
if (rootNode) {
  ReactDOM.createRoot(rootNode).render(<App />);
}

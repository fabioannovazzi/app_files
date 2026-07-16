import React, { useCallback, useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom";

const apiBase = `${window.location.origin.replace(/\/$/, "")}/review/explicit-rules`;
const statusOrder = ["pending", "approved", "rejected"];
const ALL_VALUE = "__all__";

const panelStyle = {
  border: "1px solid #e5e7eb",
  borderRadius: 12,
  padding: 12,
  background: "#fff",
  marginBottom: 12,
};

const subPanelStyle = {
  border: "1px solid #e5e7eb",
  borderRadius: 10,
  padding: 10,
  background: "#f9fafb",
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

function PillGroup({ options, selectedValues, allowAll = false, single = false, onChange }) {
  const toggle = (value) => {
    if (single) {
      onChange(new Set([value]));
      return;
    }
    const next = new Set(selectedValues);
    if (value === ALL_VALUE && allowAll) {
      next.clear();
      next.add(ALL_VALUE);
    } else {
      if (next.has(value)) {
        next.delete(value);
      } else {
        next.add(value);
      }
      if (allowAll) {
        next.delete(ALL_VALUE);
      }
      if (!next.size && allowAll) {
        next.add(ALL_VALUE);
      }
    }
    onChange(next);
  };

  if (!options.length) {
    return <span style={{ color: "#9ca3af", fontSize: 12 }}>No options</span>;
  }
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => toggle(opt.value)}
          style={{
            border: "1px solid #e5e7eb",
            borderRadius: 999,
            padding: "6px 10px",
            background: selectedValues.has(opt.value) ? "#111827" : "#fff",
            color: selectedValues.has(opt.value) ? "#fff" : "#111827",
            cursor: "pointer",
            fontSize: 13,
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
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

function ViewToggle({ active = "explicit" }) {
  return (
    <div style={{ display: "inline-flex", gap: 8, flexWrap: "wrap" }}>
      <SegmentedButton
        label="Catalog"
        active={active === "catalog"}
        onClick={() => {
          if (active !== "catalog") {
            window.location.href = "/review/page";
          }
        }}
        tooltip="See filtered products"
      />
      <SegmentedButton
        label="Coverage"
        active={active === "coverage"}
        onClick={() => {
          if (active !== "coverage") {
            window.location.href = "/review/coverage/page";
          }
        }}
        tooltip="Explore attribute coverage and N/A examples"
      />
      <SegmentedButton
        label="Explicit attributes"
        active={active === "explicit"}
        onClick={() => {
          if (active !== "explicit") {
            window.location.href = "/review/explicit-rules/page";
          }
        }}
        tooltip="Review explicit attributes"
      />
      <SegmentedButton
        label="Issues"
        active={active === "taxonomy"}
        onClick={() => {
          if (active !== "taxonomy") {
            window.location.href = "/review/issues/page";
          }
        }}
        tooltip="Find suspicious attribute issues and inspect them in Coverage"
      />
    </div>
  );
}

function statusBadge(status) {
  const key = String(status || "pending").toLowerCase();
  const palette = {
    pending: { bg: "#fef3c7", fg: "#92400e" },
    approved: { bg: "#dcfce7", fg: "#166534" },
    rejected: { bg: "#fee2e2", fg: "#991b1b" },
  }[key] || { bg: "#f3f4f6", fg: "#374151" };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        borderRadius: 999,
        padding: "2px 10px",
        background: palette.bg,
        color: palette.fg,
        textTransform: "capitalize",
        fontSize: 12,
        fontWeight: 600,
      }}
    >
      {key}
    </span>
  );
}

function compactTable(columns, rows, rowKey) {
  if (!rows.length) {
    return <div style={{ color: "#6b7280", fontSize: 13 }}>No records.</div>;
  }
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                style={{
                  textAlign: "left",
                  padding: "8px 6px",
                  borderBottom: "1px solid #e5e7eb",
                  color: "#374151",
                  background: "#f9fafb",
                  fontWeight: 600,
                }}
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${rowKey}-${index}`}>
              {columns.map((column) => (
                <td
                  key={`${rowKey}-${index}-${column.key}`}
                  style={{
                    padding: "8px 6px",
                    borderBottom: "1px solid #f3f4f6",
                    color: "#111827",
                    verticalAlign: "top",
                  }}
                >
                  {String(row[column.key] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SummaryTile({ label, value }) {
  return (
    <div style={{ ...subPanelStyle, minWidth: 180 }}>
      <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 600, color: "#111827", lineHeight: 1.1 }}>{value}</div>
    </div>
  );
}

function CandidateItem({ row, busy, onApprove, onReject }) {
  const [reviewerNote, setReviewerNote] = useState("");
  const [editedPattern, setEditedPattern] = useState(row.pattern || "");
  const [reviewedSamples, setReviewedSamples] = useState(
    Number.isFinite(Number(row.reviewed_samples)) ? Number(row.reviewed_samples) : 30
  );
  const [precisionEstimate, setPrecisionEstimate] = useState(
    Number.isFinite(Number(row.precision_estimate)) ? Number(row.precision_estimate) : 0.98
  );
  const [rejectReason, setRejectReason] = useState("");

  const snippets = Array.isArray(row.sample_snippets) ? row.sample_snippets : [];

  return (
    <div style={subPanelStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", marginBottom: 8 }}>
        <div style={{ fontWeight: 600, color: "#111827", fontSize: 13 }}>
          {row.category_key} / {row.attribute_id} / {row.proposed_value}
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>ID: {row.candidate_id}</span>
          {statusBadge(row.status)}
        </div>
      </div>

      <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
        <div>
          <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>Pattern</div>
          <input
            value={editedPattern}
            onChange={(event) => setEditedPattern(event.target.value)}
            style={inputStyle}
            placeholder="certainty pattern"
          />
        </div>
        <div>
          <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>Reviewer note</div>
          <input
            value={reviewerNote}
            onChange={(event) => setReviewerNote(event.target.value)}
            style={inputStyle}
            placeholder="review note"
          />
        </div>
        <div>
          <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>Reviewed samples</div>
          <input
            type="number"
            min={0}
            value={reviewedSamples}
            onChange={(event) => setReviewedSamples(Number(event.target.value || 0))}
            style={inputStyle}
          />
        </div>
        <div>
          <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>Precision estimate</div>
          <input
            type="number"
            min={0}
            max={1}
            step={0.01}
            value={precisionEstimate}
            onChange={(event) => setPrecisionEstimate(Number(event.target.value || 0))}
            style={inputStyle}
          />
        </div>
        <div>
          <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>Reject reason</div>
          <input
            value={rejectReason}
            onChange={(event) => setRejectReason(event.target.value)}
            style={inputStyle}
            placeholder="required for reject"
          />
        </div>
      </div>

      <div style={{ marginTop: 8, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <div style={{ fontSize: 12, color: "#6b7280" }}>
          Samples: <b>{row.sample_count || 0}</b>
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            onApprove(row.candidate_id, {
              pattern: editedPattern,
              reviewer_note: reviewerNote,
              reviewed_samples: reviewedSamples,
              precision_estimate: precisionEstimate,
            })
          }
          style={{ ...primaryButtonStyle, opacity: busy ? 0.65 : 1 }}
        >
          Approve
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            onReject(row.candidate_id, {
              reason: rejectReason || "not precise enough",
              reviewer_note: reviewerNote,
            })
          }
          style={{ ...buttonStyle, opacity: busy ? 0.65 : 1 }}
        >
          Reject
        </button>
      </div>

      {snippets.length ? (
        <details style={{ marginTop: 8 }}>
          <summary style={{ cursor: "pointer", color: "#374151", fontSize: 12 }}>
            Snippets ({snippets.length})
          </summary>
          <div style={{ marginTop: 8, display: "grid", gap: 6 }}>
            {snippets.map((snippet, idx) => (
              <div
                key={`${row.candidate_id}-snippet-${idx}`}
                style={{
                  border: "1px solid #e5e7eb",
                  borderRadius: 8,
                  padding: "8px 10px",
                  fontSize: 12,
                  background: "#fff",
                  color: "#111827",
                }}
              >
                {snippet}
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  );
}

function App() {
  const [statusFilter, setStatusFilter] = useState("pending");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [attributeFilter, setAttributeFilter] = useState("");
  const [searchFilter, setSearchFilter] = useState("");

  const [candidates, setCandidates] = useState([]);
  const [allCandidates, setAllCandidates] = useState([]);
  const [auditRows, setAuditRows] = useState([]);
  const [versions, setVersions] = useState([]);
  const [precisionRows, setPrecisionRows] = useState([]);

  const [configText, setConfigText] = useState("{}");
  const [publishNote, setPublishNote] = useState("");
  const [validation, setValidation] = useState(null);

  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [actionCandidateId, setActionCandidateId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const statusPillSelection = useMemo(
    () => new Set([statusFilter || ALL_VALUE]),
    [statusFilter]
  );

  const loadCandidateIndex = useCallback(async () => {
    const payload = await fetchJson(`${apiBase}/candidates?limit=2000`);
    setAllCandidates(payload.candidates || []);
  }, []);

  const loadCandidates = useCallback(async () => {
    setLoadingCandidates(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      if (categoryFilter) params.set("category_key", categoryFilter);
      if (attributeFilter) params.set("attribute_id", attributeFilter);
      params.set("limit", "600");
      const payload = await fetchJson(`${apiBase}/candidates?${params.toString()}`);
      setCandidates(payload.candidates || []);
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setLoadingCandidates(false);
    }
  }, [statusFilter, categoryFilter, attributeFilter]);

  const loadAudit = useCallback(async () => {
    try {
      const payload = await fetchJson(`${apiBase}/audit?limit=200`);
      setAuditRows(payload.audit || []);
      setVersions(payload.versions || []);
      setPrecisionRows(payload.precision_metrics || []);
    } catch (err) {
      setError(String(err.message || err));
    }
  }, []);

  const loadConfig = useCallback(async () => {
    try {
      const payload = await fetchJson(`${apiBase}/config`);
      setConfigText(JSON.stringify(payload.config || {}, null, 2));
    } catch (err) {
      setError(String(err.message || err));
    }
  }, []);

  useEffect(() => {
    loadCandidates();
  }, [loadCandidates]);

  useEffect(() => {
    loadCandidateIndex();
    loadAudit();
    loadConfig();
  }, [loadAudit, loadCandidateIndex, loadConfig]);

  const categoryOptions = useMemo(
    () => [...new Set(allCandidates.map((row) => row.category_key).filter(Boolean))].sort(),
    [allCandidates]
  );
  const attributeOptions = useMemo(
    () => [...new Set(allCandidates.map((row) => row.attribute_id).filter(Boolean))].sort(),
    [allCandidates]
  );
  const categoryPillSelection = useMemo(
    () => new Set([categoryFilter || ALL_VALUE]),
    [categoryFilter]
  );
  const attributePillSelection = useMemo(
    () => new Set([attributeFilter || ALL_VALUE]),
    [attributeFilter]
  );

  const statusCounts = useMemo(() => {
    const counts = { pending: 0, approved: 0, rejected: 0 };
    allCandidates.forEach((row) => {
      const key = String(row.status || "pending").toLowerCase();
      if (counts[key] === undefined) return;
      counts[key] += 1;
    });
    return counts;
  }, [allCandidates]);

  const visibleCandidates = useMemo(() => {
    const token = searchFilter.trim().toLowerCase();
    if (!token) return candidates;
    return candidates.filter((row) => {
      const haystack = [row.candidate_id, row.category_key, row.attribute_id, row.proposed_value, row.pattern]
        .map((value) => String(value || "").toLowerCase())
        .join(" ");
      return haystack.includes(token);
    });
  }, [candidates, searchFilter]);

  const approveCandidate = async (candidateId, body) => {
    setError("");
    setNotice("");
    setActionCandidateId(candidateId);
    try {
      await fetchJson(`${apiBase}/candidates/${encodeURIComponent(candidateId)}/approve`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setNotice(`Candidate approved: ${candidateId}`);
      await loadCandidates();
      await loadCandidateIndex();
      await loadAudit();
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setActionCandidateId("");
    }
  };

  const rejectCandidate = async (candidateId, body) => {
    setError("");
    setNotice("");
    setActionCandidateId(candidateId);
    try {
      await fetchJson(`${apiBase}/candidates/${encodeURIComponent(candidateId)}/reject`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setNotice(`Candidate rejected: ${candidateId}`);
      await loadCandidates();
      await loadCandidateIndex();
      await loadAudit();
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setActionCandidateId("");
    }
  };

  const validateConfig = async () => {
    setError("");
    setNotice("");
    try {
      const config = JSON.parse(configText || "{}");
      const payload = await fetchJson(`${apiBase}/config/validate`, {
        method: "POST",
        body: JSON.stringify({ config }),
      });
      setValidation(payload);
      if (payload.valid) {
        setNotice("Config validation passed.");
      }
    } catch (err) {
      setError(String(err.message || err));
    }
  };

  const publishConfig = async () => {
    setError("");
    setNotice("");
    try {
      const config = JSON.parse(configText || "{}");
      const payload = await fetchJson(`${apiBase}/config/publish`, {
        method: "POST",
        body: JSON.stringify({
          config,
          note: publishNote || null,
        }),
      });
      setNotice(`Published ruleset ${payload.version}`);
      await loadAudit();
      await loadConfig();
      await loadCandidateIndex();
    } catch (err) {
      setError(String(err.message || err));
    }
  };

  return (
    <div style={{ fontSize: 13, lineHeight: 1.35 }}>
      <div style={{ ...panelStyle, width: "fit-content", maxWidth: "100%" }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 8 }}>Settings</div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ ...subPanelStyle }}>
            <ViewToggle active="explicit" />
          </div>
        </div>
      </div>

      <div style={panelStyle}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 4 }}>
          Explicit Attribute Rules
        </div>
        <div style={{ color: "#4b5563", fontSize: 12, marginBottom: 10 }}>
          Use exact PDP phrases to assign values. If the phrase is present, we assign the value; if not, we keep N/A.
        </div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <SummaryTile label="Pending" value={statusCounts.pending} />
          <SummaryTile label="Approved" value={statusCounts.approved} />
          <SummaryTile label="Rejected" value={statusCounts.rejected} />
          <SummaryTile label="Visible" value={visibleCandidates.length} />
        </div>

        {error ? (
          <div
            style={{
              border: "1px solid #fecaca",
              background: "#fef2f2",
              color: "#991b1b",
              borderRadius: 8,
              padding: "8px 10px",
              marginTop: 10,
            }}
          >
            {error}
          </div>
        ) : null}

        {notice ? (
          <div
            style={{
              border: "1px solid #bbf7d0",
              background: "#f0fdf4",
              color: "#166534",
              borderRadius: 8,
              padding: "8px 10px",
              marginTop: 10,
            }}
          >
            {notice}
          </div>
        ) : null}
      </div>

      <div style={panelStyle}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 8 }}>Candidates</div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 10 }}>
          <div style={{ ...subPanelStyle, minWidth: 260, flex: "1 1 260px" }}>
            <div style={{ fontSize: 12, marginBottom: 4, color: "#6b7280" }}>Status</div>
            <PillGroup
              options={[{ value: ALL_VALUE, label: "all" }, ...statusOrder.map((status) => ({ value: status, label: status }))]}
              selectedValues={statusPillSelection}
              allowAll
              single
              onChange={(vals) => {
                const [next] = Array.from(vals);
                setStatusFilter(next === ALL_VALUE ? "" : next || "");
              }}
            />
          </div>

          <div style={{ ...subPanelStyle, minWidth: 280, flex: "1 1 280px" }}>
            <div style={{ fontSize: 12, marginBottom: 4, color: "#6b7280" }}>Category</div>
            <PillGroup
              options={[
                { value: ALL_VALUE, label: "all categories" },
                ...categoryOptions.map((value) => ({ value, label: value })),
              ]}
              selectedValues={categoryPillSelection}
              allowAll
              single
              onChange={(vals) => {
                const [next] = Array.from(vals);
                setCategoryFilter(next === ALL_VALUE ? "" : next || "");
              }}
            />
          </div>

          <div style={{ ...subPanelStyle, minWidth: 280, flex: "1 1 280px" }}>
            <div style={{ fontSize: 12, marginBottom: 4, color: "#6b7280" }}>Attribute</div>
            <PillGroup
              options={[
                { value: ALL_VALUE, label: "all attributes" },
                ...attributeOptions.map((value) => ({ value, label: value })),
              ]}
              selectedValues={attributePillSelection}
              allowAll
              single
              onChange={(vals) => {
                const [next] = Array.from(vals);
                setAttributeFilter(next === ALL_VALUE ? "" : next || "");
              }}
            />
          </div>

          <div style={{ ...subPanelStyle, minWidth: 220, flex: "1 1 220px" }}>
            <div style={{ fontSize: 12, marginBottom: 4, color: "#6b7280" }}>Search</div>
            <input
              style={inputStyle}
              value={searchFilter}
              onChange={(event) => setSearchFilter(event.target.value)}
              placeholder="candidate id / pattern / value"
            />
          </div>

          <button type="button" onClick={loadCandidates} disabled={loadingCandidates} style={primaryButtonStyle}>
            {loadingCandidates ? "Loading..." : "Refresh"}
          </button>
        </div>

        <div style={{ display: "grid", gap: 10 }}>
          {visibleCandidates.length ? (
            visibleCandidates.map((row) => (
              <CandidateItem
                key={row.candidate_id}
                row={row}
                busy={actionCandidateId === row.candidate_id}
                onApprove={approveCandidate}
                onReject={rejectCandidate}
              />
            ))
          ) : (
            <div style={{ ...subPanelStyle, textAlign: "center", color: "#6b7280" }}>
              No candidates found for current filters.
            </div>
          )}
        </div>
      </div>

      <div style={panelStyle}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 8 }}>Config</div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 10 }}>
          <div style={{ ...subPanelStyle, minWidth: 220, flex: "1 1 220px" }}>
            <div style={{ fontSize: 12, marginBottom: 4, color: "#6b7280" }}>Note</div>
            <input
              style={inputStyle}
              value={publishNote}
              onChange={(event) => setPublishNote(event.target.value)}
              placeholder="publish note"
            />
          </div>

          <button type="button" onClick={validateConfig} style={buttonStyle}>
            Validate
          </button>
          <button type="button" onClick={publishConfig} style={primaryButtonStyle}>
            Publish
          </button>
          <button type="button" onClick={loadConfig} style={buttonStyle}>
            Reload
          </button>
        </div>

        <textarea
          value={configText}
          onChange={(event) => setConfigText(event.target.value)}
          style={{
            width: "100%",
            minHeight: 340,
            fontFamily: '"SFMono-Regular", Menlo, monospace',
            fontSize: 12,
            border: "1px solid #d1d5db",
            borderRadius: 8,
            padding: 10,
            background: "#f9fafb",
          }}
        />

        {validation ? (
          <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "#111827" }}>
              Validation: {validation.valid ? "PASS" : "FAIL"}
            </div>

            {validation.errors && validation.errors.length ? (
              <div style={{ border: "1px solid #fecaca", background: "#fef2f2", borderRadius: 8, padding: 10 }}>
                <div style={{ fontWeight: 600, color: "#991b1b", marginBottom: 6, fontSize: 12 }}>Errors</div>
                <ul style={{ margin: 0, paddingLeft: 20, color: "#991b1b", fontSize: 12 }}>
                  {validation.errors.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {validation.warnings && validation.warnings.length ? (
              <div style={{ border: "1px solid #fde68a", background: "#fffbeb", borderRadius: 8, padding: 10 }}>
                <div style={{ fontWeight: 600, color: "#92400e", marginBottom: 6, fontSize: 12 }}>Warnings</div>
                <ul style={{ margin: 0, paddingLeft: 20, color: "#92400e", fontSize: 12 }}>
                  {validation.warnings.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      <div style={panelStyle}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 8 }}>Audit & Metrics</div>

        <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
          <div style={subPanelStyle}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 8 }}>Config versions</div>
            {compactTable(
              [
                { key: "version", label: "Version" },
                { key: "published_at", label: "Published" },
                { key: "actor", label: "Actor" },
              ],
              versions.slice(0, 12),
              "versions"
            )}
          </div>

          <div style={subPanelStyle}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 8 }}>Recent actions</div>
            {compactTable(
              [
                { key: "timestamp", label: "Timestamp" },
                { key: "action", label: "Action" },
                { key: "candidate_id", label: "Candidate" },
              ],
              auditRows.slice(0, 15),
              "audit"
            )}
          </div>

          <div style={subPanelStyle}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 8 }}>Precision proxy</div>
            {compactTable(
              [
                { key: "category_key", label: "Category" },
                { key: "attribute_id", label: "Attribute" },
                { key: "explicit_positive_count", label: "Explicit+" },
                { key: "deterministic_precision_proxy", label: "Det" },
                { key: "llm_precision_proxy", label: "LLM" },
              ],
              precisionRows.slice(0, 15),
              "precision"
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

ReactDOM.render(<App />, document.getElementById("reactExplicitRulesApp"));

import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom";

const apiBase = `${window.location.origin.replace(/\/$/, "")}/review/deterministic-policy`;
const applicableCandidateTypes = new Set([
  "disable_bare_label",
  "block_bad_source",
  "add_deterministic_expression",
]);

const panelStyle = {
  border: "1px solid #e5e7eb",
  borderRadius: 12,
  padding: 12,
  background: "#fff",
  marginBottom: 12,
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

const inputStyle = {
  width: "100%",
  border: "1px solid #d1d5db",
  borderRadius: 10,
  padding: "8px 10px",
  fontSize: 13,
  background: "#fff",
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

function statusBadge(status) {
  const key = String(status || "open").toLowerCase();
  const palette = {
    open: { bg: "#fef3c7", fg: "#92400e" },
    approved: { bg: "#dcfce7", fg: "#166534" },
    rejected: { bg: "#fee2e2", fg: "#991b1b" },
    applied: { bg: "#dbeafe", fg: "#1d4ed8" },
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

function App() {
  const [config, setConfig] = useState(null);
  const [draft, setDraft] = useState(null);
  const [items, setItems] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState(null);
  const [preview, setPreview] = useState(null);
  const [runSummary, setRunSummary] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({ status: "open" });
  const [decision, setDecision] = useState({ reason: "" });
  const [draftPublish, setDraftPublish] = useState({ note: "" });

  const fetchConfig = async () => {
    const payload = await fetchJson(`${apiBase}/config`);
    setConfig(payload.config || null);
  };

  const fetchDraft = async () => {
    const payload = await fetchJson(`${apiBase}/draft/preview`);
    setDraft(payload);
  };

  const fetchItems = async () => {
    const params = new URLSearchParams();
    if (filters.status) params.set("status", filters.status);
    const payload = await fetchJson(`${apiBase}/queue/items?${params.toString()}`);
    const nextItems = Array.isArray(payload.items) ? payload.items : [];
    setItems(nextItems);
    if (nextItems.length) {
      setSelectedId((current) =>
        current && nextItems.some((item) => item.queue_item_id === current)
          ? current
          : nextItems[0].queue_item_id
      );
    } else {
      setSelectedId("");
      setDetail(null);
    }
  };

  const fetchDetail = async (queueItemId) => {
    if (!queueItemId) {
      setDetail(null);
      setPreview(null);
      return;
    }
    const payload = await fetchJson(`${apiBase}/queue/items/${queueItemId}`);
    setDetail(payload);
    setPreview(null);
  };

  useEffect(() => {
    Promise.all([fetchConfig(), fetchDraft(), fetchItems()]).catch((err) => {
      setError(String(err.message || err));
    });
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    fetchDetail(selectedId).catch((err) => {
      setError(String(err.message || err));
    });
  }, [selectedId]);

  useEffect(() => {
    fetchItems().catch((err) => {
      setError(String(err.message || err));
    });
  }, [filters.status]);

  const runQueue = async () => {
    setBusy(true);
    setError("");
    try {
      const payload = await fetchJson(`${apiBase}/queue/run`, { method: "POST" });
      setRunSummary(payload);
      await fetchDraft();
      await fetchItems();
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  };

  const resetDraft = async () => {
    setBusy(true);
    setError("");
    try {
      await fetchJson(`${apiBase}/draft/reset`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      await fetchConfig();
      await fetchDraft();
      await fetchItems();
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  };

  const publishDraft = async () => {
    setBusy(true);
    setError("");
    try {
      await fetchJson(`${apiBase}/draft/publish`, {
        method: "POST",
        body: JSON.stringify({
          note: draftPublish.note || null,
        }),
      });
      await fetchConfig();
      await fetchDraft();
      await fetchItems();
      setDraftPublish((current) => ({ ...current, note: "" }));
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  };

  const decide = async (nextStatus) => {
    if (!selectedId) return;
    setBusy(true);
    setError("");
    try {
      await fetchJson(`${apiBase}/queue/items/${selectedId}/${nextStatus}`, {
        method: "POST",
        body: JSON.stringify({
          decision_reason: decision.reason || null,
        }),
      });
      await fetchItems();
      await fetchDetail(selectedId);
      setDecision((current) => ({ ...current, reason: "" }));
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  };

  const applyToDraft = async () => {
    if (!selectedId) return;
    setBusy(true);
    setError("");
    try {
      await fetchJson(`${apiBase}/queue/items/${selectedId}/apply`, {
        method: "POST",
        body: JSON.stringify({
          decision_reason: decision.reason || null,
        }),
      });
      await fetchConfig();
      await fetchDraft();
      await fetchItems();
      await fetchDetail(selectedId);
      setDecision((current) => ({ ...current, reason: "" }));
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  };

  const previewApply = async () => {
    if (!selectedId) return;
    setBusy(true);
    setError("");
    try {
      const payload = await fetchJson(`${apiBase}/queue/items/${selectedId}/preview-apply`);
      setPreview(payload);
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <section style={panelStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: 22, fontWeight: 700, color: "#111827", marginBottom: 4 }}>
              Deterministic policy
            </div>
            <div style={{ fontSize: 13, color: "#6b7280" }}>
              Review read-only deterministic-policy candidates before any mutation workflow is enabled.
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="button" style={primaryButtonStyle} onClick={runQueue} disabled={busy}>
              Run queue
            </button>
            <button
              type="button"
              style={buttonStyle}
              onClick={resetDraft}
              disabled={busy || !draft?.has_draft}
            >
              Reset draft
            </button>
            <button
              type="button"
              style={buttonStyle}
              onClick={publishDraft}
              disabled={busy || !draft?.has_draft}
            >
              Publish draft
            </button>
          </div>
        </div>
      </section>

      {error ? (
        <section style={{ ...panelStyle, borderColor: "#fecaca", background: "#fef2f2", color: "#991b1b" }}>
          {error}
        </section>
      ) : null}

      <section style={panelStyle}>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 12, color: "#6b7280" }}>Published policy version</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#111827" }}>
              {config?.version || "—"}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: "#6b7280" }}>Draft present</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#111827" }}>
              {draft?.has_draft ? "yes" : "no"}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: "#6b7280" }}>Draft changed items</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#111827" }}>
              {draft?.diff_summary?.changed_item_count || 0}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: "#6b7280" }}>Open items</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#111827" }}>
              {items.length}
            </div>
          </div>
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 1fr)",
            gap: 8,
            alignItems: "center",
            marginTop: 12,
          }}
        >
          <input
            value={draftPublish.note}
            onChange={(event) =>
              setDraftPublish((current) => ({ ...current, note: event.target.value }))
            }
            style={inputStyle}
            placeholder="draft publish note"
          />
        </div>
        {runSummary ? (
          <div style={{ marginTop: 10, fontSize: 12, color: "#6b7280" }}>
            Last run: {runSummary.run_id} · source: {runSummary.config_source} · surfaced: {runSummary.surfaced_count}
          </div>
        ) : null}
        {Array.isArray(draft?.warnings) && draft.warnings.length ? (
          <div style={{ marginTop: 10, display: "grid", gap: 6 }}>
            {draft.warnings.map((warning, index) => (
              <div key={`draft-warning-${index}`} style={{ fontSize: 12, color: "#92400e" }}>
                {warning}
              </div>
            ))}
          </div>
        ) : null}
      </section>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 360px) minmax(0, 1fr)", gap: 12 }}>
        <section style={panelStyle}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center", marginBottom: 8 }}>
            <div style={{ fontWeight: 600, color: "#111827" }}>Queue</div>
            <select
              value={filters.status}
              onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}
              style={{ ...inputStyle, width: 140 }}
              data-native-select="true"
            >
              <option value="open">Open</option>
              <option value="">All</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>
          <div style={{ display: "grid", gap: 8 }}>
            {items.map((item) => (
              <button
                key={item.queue_item_id}
                type="button"
                onClick={() => setSelectedId(item.queue_item_id)}
                style={{
                  ...panelStyle,
                  marginBottom: 0,
                  textAlign: "left",
                  cursor: "pointer",
                  borderColor: selectedId === item.queue_item_id ? "#111827" : "#e5e7eb",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#111827" }}>{item.title}</div>
                  {statusBadge(item.status)}
                </div>
                <div style={{ fontSize: 12, color: "#6b7280", marginTop: 4 }}>
                  {item.category_key || "—"} / {item.attribute_id || "—"} / {item.value_id || "—"}
                </div>
                <div style={{ fontSize: 12, color: "#6b7280", marginTop: 4 }}>{item.short_reason}</div>
              </button>
            ))}
            {!items.length ? <div style={{ fontSize: 13, color: "#6b7280" }}>No queue items.</div> : null}
          </div>
        </section>

        <section style={panelStyle}>
          <div style={{ fontWeight: 600, color: "#111827", marginBottom: 8 }}>Detail</div>
          {!detail ? (
            <div style={{ fontSize: 13, color: "#6b7280" }}>Select a queue item.</div>
          ) : (
            <div style={{ display: "grid", gap: 12 }}>
              {(() => {
                const canApply =
                  detail.item.status === "approved" &&
                  applicableCandidateTypes.has(detail.item.candidate_type);
                return (
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <button
                      type="button"
                      style={buttonStyle}
                      onClick={previewApply}
                      disabled={busy || !applicableCandidateTypes.has(detail.item.candidate_type)}
                    >
                      Preview draft impact
                    </button>
                    <button
                      type="button"
                      style={buttonStyle}
                      onClick={applyToDraft}
                      disabled={busy || !canApply}
                    >
                      Apply to draft
                    </button>
                  </div>
                );
              })()}

              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
                <div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: "#111827" }}>{detail.item.title}</div>
                  <div style={{ fontSize: 12, color: "#6b7280" }}>
                    {detail.item.candidate_type} · {detail.item.category_key} / {detail.item.attribute_id} / {detail.item.value_id || "—"}
                  </div>
                </div>
                {statusBadge(detail.item.status)}
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
                <div style={panelStyle}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", marginBottom: 6 }}>Policy context</div>
                  <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: 12, color: "#111827" }}>
                    {JSON.stringify(detail.policy_context || {}, null, 2)}
                  </pre>
                </div>
                <div style={panelStyle}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", marginBottom: 6 }}>Taxonomy context</div>
                  <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 6 }}>
                    {detail.taxonomy_context?.attribute_label || detail.item.attribute_id} · values: {detail.taxonomy_context?.values?.length || 0}
                  </div>
                  <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: 12, color: "#111827" }}>
                    {JSON.stringify(detail.taxonomy_context?.values || [], null, 2)}
                  </pre>
                </div>
              </div>

              <div style={panelStyle}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", marginBottom: 6 }}>Aggregated evidence</div>
                <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: 12, color: "#111827" }}>
                  {JSON.stringify(detail.aggregated || {}, null, 2)}
                </pre>
              </div>

              {preview ? (
                <div style={panelStyle}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", marginBottom: 6 }}>
                    Preview draft impact
                  </div>
                  <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 8 }}>
                    apply supported: {preview.apply_supported ? "yes" : "no"} · changed items:{" "}
                    {preview.preview?.diff_summary?.changed_item_count || 0}
                  </div>
                  <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: 12, color: "#111827" }}>
                    {JSON.stringify(preview.mutation_summary || {}, null, 2)}
                  </pre>
                  {Array.isArray(preview.warnings) && preview.warnings.length ? (
                    <div style={{ marginTop: 10, display: "grid", gap: 6 }}>
                      {preview.warnings.map((warning, index) => (
                        <div key={`preview-warning-${index}`} style={{ fontSize: 12, color: "#92400e" }}>
                          {warning}
                        </div>
                      ))}
                    </div>
                  ) : null}
                  <div style={{ marginTop: 10 }}>
                    <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: 12, color: "#111827" }}>
                      {JSON.stringify(preview.preview || {}, null, 2)}
                    </pre>
                  </div>
                </div>
              ) : null}

              <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: 8, alignItems: "center" }}>
                <input
                  value={decision.reason}
                  onChange={(event) => setDecision((current) => ({ ...current, reason: event.target.value }))}
                  style={inputStyle}
                  placeholder="decision reason"
                />
              </div>

              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                  type="button"
                  style={primaryButtonStyle}
                  onClick={() => decide("approve")}
                  disabled={busy || detail.item.status === "approved"}
                >
                  Approve
                </button>
                <button
                  type="button"
                  style={buttonStyle}
                  onClick={() => decide("reject")}
                  disabled={busy || detail.item.status === "rejected"}
                >
                  Reject
                </button>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

const root = document.getElementById("reactDeterministicPolicyQueueApp");
if (root) {
  ReactDOM.createRoot(root).render(<App />);
}

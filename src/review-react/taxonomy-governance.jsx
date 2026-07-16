import React, { useCallback, useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom";

const apiBase = `${window.location.origin.replace(/\/$/, "")}/review/taxonomy`;
const GOVERNANCE_STATUSES = ["active", "draft", "needs_review", "deprecated"];

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
    const error = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    error.detail = detail;
    error.status = response.status;
    throw error;
  }
  return payload;
}

function cloneConfig(config) {
  return JSON.parse(JSON.stringify(config || {}));
}

function normalizeLeafId(value) {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, "_");
}

function isReservedLeaf(leafId) {
  return leafId === "unknown" || leafId === "other";
}

function normalizeLeafStatus(node) {
  const leafId = normalizeLeafId(node && (node.id || node.label));
  if (isReservedLeaf(leafId)) {
    return "active";
  }
  const status = String((node && node.status) || "active").trim().toLowerCase();
  return GOVERNANCE_STATUSES.includes(status) ? status : "active";
}

function flattenTaxonomy(config) {
  const categories = Array.isArray(config && config.categories) ? config.categories : [];
  const rows = [];
  let attributeCount = 0;

  const walkNodes = ({ categoryKey, categoryLabel, attributeId, attributeLabel, nodes }) => {
    (Array.isArray(nodes) ? nodes : []).forEach((node) => {
      if (!node || typeof node !== "object") return;
      const children = Array.isArray(node.children) ? node.children : [];
      if (children.length) {
        walkNodes({
          categoryKey,
          categoryLabel,
          attributeId,
          attributeLabel,
          nodes: children,
        });
        return;
      }
      const leafId = normalizeLeafId(node.id || node.label);
      const label = String(node.label || node.id || "").trim();
      const reserved = isReservedLeaf(leafId);
      rows.push({
        category_key: categoryKey,
        category_label: categoryLabel,
        attribute_id: attributeId,
        attribute_label: attributeLabel,
        leaf_id: leafId,
        label,
        status: normalizeLeafStatus(node),
        governance_action: String(
          node.governance_action ||
            ((Array.isArray(node.successor_leaf_ids) && node.successor_leaf_ids.length)
              ? (node.successor_leaf_ids.length === 1 ? "merge" : "split")
              : (node.replacement_leaf_id ? "merge" : ""))
        ).trim(),
        successor_leaf_ids: (
          Array.isArray(node.successor_leaf_ids)
            ? node.successor_leaf_ids
            : (node.replacement_leaf_id ? [node.replacement_leaf_id] : [])
        )
          .map((value) => normalizeLeafId(value))
          .filter(Boolean),
        governance_reason: String(node.governance_reason || "").trim(),
        reserved,
      });
    });
  };

  categories.forEach((category) => {
    if (!category || typeof category !== "object") return;
    const categoryKey = normalizeLeafId(category.id || category.label);
    const categoryLabel = String(category.label || category.id || categoryKey).trim();
    const attributes = Array.isArray(category.attributes) ? category.attributes : [];
    attributeCount += attributes.length;
    attributes.forEach((attribute) => {
      if (!attribute || typeof attribute !== "object") return;
      const attributeId = normalizeLeafId(attribute.id || attribute.label);
      const attributeLabel = String(attribute.label || attribute.id || attributeId).trim();
      walkNodes({
        categoryKey,
        categoryLabel,
        attributeId,
        attributeLabel,
        nodes: Array.isArray(attribute.nodes) ? attribute.nodes : [],
      });
    });
  });

  return {
    categoryCount: categories.length,
    attributeCount,
    rows,
  };
}

function updateLeafGovernance(config, payload) {
  const nextConfig = cloneConfig(config);
  const categories = Array.isArray(nextConfig.categories) ? nextConfig.categories : [];
  let updated = false;

  const normalizedCategory = normalizeLeafId(payload.categoryKey);
  const normalizedAttribute = normalizeLeafId(payload.attributeId);
  const normalizedLeaf = normalizeLeafId(payload.leafId);

  const applyToNodes = (nodes) => {
    (Array.isArray(nodes) ? nodes : []).forEach((node) => {
      if (!node || typeof node !== "object") return;
      const children = Array.isArray(node.children) ? node.children : [];
      if (children.length) {
        applyToNodes(children);
        return;
      }
      const nodeLeafId = normalizeLeafId(node.id || node.label);
      if (nodeLeafId !== normalizedLeaf) {
        return;
      }
      const nextStatus = GOVERNANCE_STATUSES.includes(payload.status) ? payload.status : "active";
      const nextAction = nextStatus === "active" ? "" : String(payload.governanceAction || "").trim().toLowerCase();
      const nextSuccessors = nextStatus === "active"
        ? []
        : Array.from(
            new Set(
              (Array.isArray(payload.successorLeafIds) ? payload.successorLeafIds : [])
                .map((value) => normalizeLeafId(value))
                .filter(Boolean)
            )
          );
      const nextReason = String(payload.governanceReason || "").trim();
      if (nextStatus === "active") {
        delete node.status;
      } else {
        node.status = nextStatus;
      }
      if (nextAction) {
        node.governance_action = nextAction;
      } else {
        delete node.governance_action;
      }
      if (nextSuccessors.length) {
        node.successor_leaf_ids = nextSuccessors;
      } else {
        delete node.successor_leaf_ids;
      }
      if (nextReason) {
        node.governance_reason = nextReason;
      } else {
        delete node.governance_reason;
      }
      delete node.replacement_leaf_id;
      updated = true;
    });
  };

  categories.forEach((category) => {
    if (normalizeLeafId(category && (category.id || category.label)) !== normalizedCategory) {
      return;
    }
    const attributes = Array.isArray(category.attributes) ? category.attributes : [];
    attributes.forEach((attribute) => {
      if (normalizeLeafId(attribute && (attribute.id || attribute.label)) !== normalizedAttribute) {
        return;
      }
      applyToNodes(attribute.nodes || []);
    });
  });

  if (!updated) {
    throw new Error(`Leaf not found: ${normalizedCategory}/${normalizedAttribute}/${normalizedLeaf}`);
  }

  return nextConfig;
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
    <div style={{ ...subPanelStyle, minWidth: 160 }}>
      <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 600, color: "#111827", lineHeight: 1.1 }}>{value}</div>
    </div>
  );
}

function statusBadge(status) {
  const key = String(status || "active").toLowerCase();
  const palette = {
    active: { bg: "#dcfce7", fg: "#166534" },
    draft: { bg: "#e0f2fe", fg: "#075985" },
    needs_review: { bg: "#fef3c7", fg: "#92400e" },
    deprecated: { bg: "#fee2e2", fg: "#991b1b" },
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
      {key.replace(/_/g, " ")}
    </span>
  );
}

function formatImpactReason(reason) {
  const labels = {
    unknown_category: "Unknown category",
    unknown_attribute: "Unknown attribute",
    unknown_canonical_value: "Unknown canonical value",
    inactive_canonical_value: "Canonical value not active",
  };
  return labels[String(reason || "").trim()] || String(reason || "");
}

function App() {
  const [draftConfig, setDraftConfig] = useState({ categories: [] });
  const [configPath, setConfigPath] = useState("");
  const [publishActor, setPublishActor] = useState("review-ui");
  const [publishNote, setPublishNote] = useState("");
  const [publishVersion, setPublishVersion] = useState("");
  const [validation, setValidation] = useState(null);
  const [preview, setPreview] = useState(null);
  const [acknowledgeInvalidExplicitRules, setAcknowledgeInvalidExplicitRules] = useState(false);
  const [auditRows, setAuditRows] = useState([]);
  const [versions, setVersions] = useState([]);
  const [statusFilter, setStatusFilter] = useState("changed");
  const [searchFilter, setSearchFilter] = useState("");
  const [selectedCategoryKey, setSelectedCategoryKey] = useState("");
  const [selectedAttributeId, setSelectedAttributeId] = useState("");
  const [selectedLeafId, setSelectedLeafId] = useState("");
  const [editorStatus, setEditorStatus] = useState("active");
  const [editorAction, setEditorAction] = useState("");
  const [editorSuccessorLeafIds, setEditorSuccessorLeafIds] = useState([]);
  const [editorReason, setEditorReason] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const applyDraftConfig = useCallback((nextConfig, noticeMessage = "") => {
    setDraftConfig(nextConfig || { categories: [] });
    setValidation(null);
    setPreview(null);
    setAcknowledgeInvalidExplicitRules(false);
    if (noticeMessage) {
      setNotice(noticeMessage);
    }
  }, []);

  const loadConfig = useCallback(async () => {
    try {
      const payload = await fetchJson(`${apiBase}/config`);
      setConfigPath(String(payload.path || ""));
      setError("");
      setNotice("");
      applyDraftConfig(payload.config || { categories: [] });
    } catch (err) {
      setError(String(err.message || err));
    }
  }, [applyDraftConfig]);

  const loadAudit = useCallback(async () => {
    try {
      const payload = await fetchJson(`${apiBase}/audit?limit=200`);
      setAuditRows(payload.audit || []);
      setVersions(payload.versions || []);
    } catch (err) {
      setError(String(err.message || err));
    }
  }, []);

  useEffect(() => {
    loadConfig();
    loadAudit();
  }, [loadConfig, loadAudit]);

  const flattened = useMemo(() => flattenTaxonomy(draftConfig || {}), [draftConfig]);

  const governableRows = useMemo(
    () => flattened.rows.filter((row) => !row.reserved),
    [flattened.rows]
  );

  const categoryOptions = useMemo(
    () => Array.from(new Map(governableRows.map((row) => [row.category_key, row.category_label])).entries())
      .map(([value, label]) => ({ value, label }))
      .sort((left, right) => left.label.localeCompare(right.label)),
    [governableRows]
  );

  useEffect(() => {
    if (!categoryOptions.length) {
      if (selectedCategoryKey) setSelectedCategoryKey("");
      return;
    }
    if (!categoryOptions.some((option) => option.value === selectedCategoryKey)) {
      setSelectedCategoryKey(categoryOptions[0].value);
    }
  }, [categoryOptions, selectedCategoryKey]);

  const attributeOptions = useMemo(
    () => Array.from(
      new Map(
        governableRows
          .filter((row) => row.category_key === selectedCategoryKey)
          .map((row) => [row.attribute_id, row.attribute_label])
      ).entries()
    )
      .map(([value, label]) => ({ value, label }))
      .sort((left, right) => left.label.localeCompare(right.label)),
    [governableRows, selectedCategoryKey]
  );

  useEffect(() => {
    if (!attributeOptions.length) {
      if (selectedAttributeId) setSelectedAttributeId("");
      return;
    }
    if (!attributeOptions.some((option) => option.value === selectedAttributeId)) {
      setSelectedAttributeId(attributeOptions[0].value);
    }
  }, [attributeOptions, selectedAttributeId]);

  const leafOptions = useMemo(
    () => governableRows
      .filter(
        (row) =>
          row.category_key === selectedCategoryKey && row.attribute_id === selectedAttributeId
      )
      .map((row) => ({
        value: row.leaf_id,
        label: row.label || row.leaf_id,
        status: row.status,
      }))
      .sort((left, right) => left.label.localeCompare(right.label)),
    [governableRows, selectedAttributeId, selectedCategoryKey]
  );

  useEffect(() => {
    if (!leafOptions.length) {
      if (selectedLeafId) setSelectedLeafId("");
      return;
    }
    if (!leafOptions.some((option) => option.value === selectedLeafId)) {
      setSelectedLeafId(leafOptions[0].value);
    }
  }, [leafOptions, selectedLeafId]);

  const selectedRow = useMemo(
    () =>
      governableRows.find(
        (row) =>
          row.category_key === selectedCategoryKey &&
          row.attribute_id === selectedAttributeId &&
          row.leaf_id === selectedLeafId
      ) || null,
    [governableRows, selectedAttributeId, selectedCategoryKey, selectedLeafId]
  );

  const selectedAttributeSelection = useMemo(() => {
    const categories = Array.isArray(draftConfig && draftConfig.categories)
      ? draftConfig.categories
      : [];
    for (const category of categories) {
      if (normalizeLeafId(category && (category.id || category.label)) !== selectedCategoryKey) {
        continue;
      }
      const attributes = Array.isArray(category && category.attributes)
        ? category.attributes
        : [];
      for (const attribute of attributes) {
        if (
          normalizeLeafId(attribute && (attribute.id || attribute.label)) ===
          selectedAttributeId
        ) {
          return String(attribute.selection || "single").trim().toLowerCase() || "single";
        }
      }
    }
    return "single";
  }, [draftConfig, selectedAttributeId, selectedCategoryKey]);

  useEffect(() => {
    if (!selectedRow) {
      setEditorStatus("active");
      setEditorAction("");
      setEditorSuccessorLeafIds([]);
      setEditorReason("");
      return;
    }
    setEditorStatus(selectedRow.status || "active");
    setEditorAction(selectedRow.governance_action || "");
    setEditorSuccessorLeafIds(Array.isArray(selectedRow.successor_leaf_ids) ? selectedRow.successor_leaf_ids : []);
    setEditorReason(selectedRow.governance_reason || "");
  }, [selectedRow]);

  const successorOptions = useMemo(
    () => governableRows
      .filter(
        (row) =>
          row.category_key === selectedCategoryKey &&
          row.attribute_id === selectedAttributeId &&
          row.leaf_id !== selectedLeafId
      )
      .map((row) => ({ value: row.leaf_id, label: row.label || row.leaf_id }))
      .sort((left, right) => left.label.localeCompare(right.label)),
    [governableRows, selectedAttributeId, selectedCategoryKey, selectedLeafId]
  );

  const summary = useMemo(() => {
    const counts = {
      categories: flattened.categoryCount,
      attributes: flattened.attributeCount,
      governable_leaves: governableRows.length,
      active: 0,
      draft: 0,
      needs_review: 0,
      deprecated: 0,
      changed: 0,
    };
    governableRows.forEach((row) => {
      const status = row.status || "active";
      if (counts[status] !== undefined) {
        counts[status] += 1;
      }
      if (
        status !== "active" ||
        row.governance_action ||
        (Array.isArray(row.successor_leaf_ids) && row.successor_leaf_ids.length) ||
        row.governance_reason
      ) {
        counts.changed += 1;
      }
    });
    return counts;
  }, [flattened.attributeCount, flattened.categoryCount, governableRows]);

  const visibleRows = useMemo(() => {
    const token = searchFilter.trim().toLowerCase();
    return governableRows.filter((row) => {
      const changed =
        row.status !== "active" ||
        row.governance_action ||
        (Array.isArray(row.successor_leaf_ids) && row.successor_leaf_ids.length) ||
        row.governance_reason;
      if (statusFilter === "changed" && !changed) return false;
      if (statusFilter !== "all" && statusFilter !== "changed" && row.status !== statusFilter) {
        return false;
      }
      if (!token) return true;
      const haystack = [
        row.category_key,
        row.category_label,
        row.attribute_id,
        row.attribute_label,
        row.leaf_id,
        row.label,
        row.status,
        row.governance_action,
        (row.successor_leaf_ids || []).join(" "),
        row.governance_reason,
      ]
        .map((value) => String(value || "").toLowerCase())
        .join(" ");
      return haystack.includes(token);
    });
  }, [governableRows, searchFilter, statusFilter]);

  const selectedChangeState = !!(
    selectedRow &&
    (
      selectedRow.status !== "active" ||
      selectedRow.governance_action ||
      (Array.isArray(selectedRow.successor_leaf_ids) && selectedRow.successor_leaf_ids.length) ||
      selectedRow.governance_reason
    )
  );

  const requiresExplicitRuleAcknowledgement =
    Number(preview?.explicit_rule_summary?.newly_invalid_active_rules || 0) > 0;

  const validateConfig = async () => {
    setError("");
    setNotice("");
    setPreview(null);
    try {
      const payload = await fetchJson(`${apiBase}/config/validate`, {
        method: "POST",
        body: JSON.stringify({ config: draftConfig }),
      });
      setValidation(payload);
      if (payload.valid) {
        setNotice("Taxonomy validation passed.");
      }
    } catch (err) {
      setError(String(err.message || err));
    }
  };

  const previewConfig = async () => {
    setError("");
    setNotice("");
    try {
      const payload = await fetchJson(`${apiBase}/config/preview`, {
        method: "POST",
        body: JSON.stringify({ config: draftConfig }),
      });
      setPreview(payload);
      setAcknowledgeInvalidExplicitRules(false);
      if (payload.valid) {
        const invalidRules = Number(
          (payload.explicit_rule_summary && payload.explicit_rule_summary.newly_invalid_rules) || 0
        );
        setNotice(
          invalidRules
            ? `Preview found ${invalidRules} newly invalid explicit rule${invalidRules === 1 ? "" : "s"}.`
            : "Preview found no newly invalid explicit rules."
        );
      }
    } catch (err) {
      setError(String(err.message || err));
    }
  };

  const applyNormalizedConfig = () => {
    if (!validation || !validation.valid || !validation.normalized_config) {
      return;
    }
    applyDraftConfig(validation.normalized_config, "Applied normalized taxonomy to the draft.");
  };

  const applySelectedLeaf = () => {
    if (!selectedRow) {
      return;
    }
    setError("");
    setNotice("");
    try {
      const nextConfig = updateLeafGovernance(draftConfig, {
        categoryKey: selectedCategoryKey,
        attributeId: selectedAttributeId,
        leafId: selectedLeafId,
        status: editorStatus,
        governanceAction: editorAction,
        successorLeafIds: editorSuccessorLeafIds,
        governanceReason: editorReason,
      });
      applyDraftConfig(
        nextConfig,
        `Updated ${selectedRow.category_key}/${selectedRow.attribute_id}/${selectedRow.leaf_id}`
      );
    } catch (err) {
      setError(String(err.message || err));
    }
  };

  const resetSelectedLeafForm = () => {
    if (!selectedRow) {
      return;
    }
    setEditorStatus(selectedRow.status || "active");
    setEditorAction(selectedRow.governance_action || "");
    setEditorSuccessorLeafIds(
      Array.isArray(selectedRow.successor_leaf_ids) ? selectedRow.successor_leaf_ids : []
    );
    setEditorReason(selectedRow.governance_reason || "");
    setNotice("Reverted unsaved leaf edits.");
  };

  const clearSelectedLeafGovernance = () => {
    if (!selectedRow) {
      return;
    }
    setEditorStatus("active");
    setEditorAction("");
    setEditorSuccessorLeafIds([]);
    setEditorReason("");
  };

  const selectedWorkflow =
    editorStatus === "active"
      ? "active"
      : editorAction === "merge"
        ? "merge"
        : editorAction === "split"
          ? "split"
          : editorStatus;

  const setLeafWorkflow = (workflow) => {
    setError("");
    setNotice("");
    if (workflow === "active") {
      setEditorStatus("active");
      setEditorAction("");
      setEditorSuccessorLeafIds([]);
      return;
    }
    if (workflow === "needs_review") {
      setEditorStatus("needs_review");
      setEditorAction("");
      setEditorSuccessorLeafIds([]);
      return;
    }
    if (workflow === "draft") {
      setEditorStatus("draft");
      setEditorAction("");
      setEditorSuccessorLeafIds([]);
      return;
    }
    if (workflow === "merge") {
      setEditorStatus("deprecated");
      setEditorAction("merge");
      setEditorSuccessorLeafIds((current) => current.slice(0, 1));
      return;
    }
    if (workflow === "split") {
      if (selectedAttributeSelection !== "multi") {
        setNotice("Split is allowed only for multi-select attributes.");
        return;
      }
      setEditorStatus("deprecated");
      setEditorAction("split");
      return;
    }
  };

  const publishConfig = async () => {
    setError("");
    setNotice("");
    try {
      const payload = await fetchJson(`${apiBase}/config/publish`, {
        method: "POST",
        body: JSON.stringify({
          config: draftConfig,
          actor: publishActor || "review-ui",
          note: publishNote || null,
          version: publishVersion || null,
          acknowledge_invalid_active_explicit_rules: acknowledgeInvalidExplicitRules,
        }),
      });
      setNotice(`Published taxonomy ${payload.version}`);
      setPublishVersion("");
      setAcknowledgeInvalidExplicitRules(false);
      await loadAudit();
      await loadConfig();
    } catch (err) {
      if (err && err.detail && typeof err.detail === "object") {
        const detail = err.detail;
        if (detail.explicit_rule_summary || detail.explicit_rule_impacts) {
          setPreview({
            valid: false,
            errors: [],
            warnings: [],
            explicit_rules_path: detail.explicit_rules_path || "",
            explicit_rule_summary: detail.explicit_rule_summary || {},
            explicit_rule_impacts: detail.explicit_rule_impacts || [],
          });
        }
        if (detail.message) {
          setError(String(detail.message));
          return;
        }
      }
      setError(String(err.message || err));
    }
  };

  const jsonSnapshot = useMemo(() => JSON.stringify(draftConfig || {}, null, 2), [draftConfig]);

  return (
    <div style={{ fontSize: 13, lineHeight: 1.35 }}>
      <div style={{ ...panelStyle, width: "fit-content", maxWidth: "100%" }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 8 }}>Settings</div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ ...subPanelStyle }}>
            <ViewToggle active="taxonomy" />
          </div>
        </div>
      </div>

      <div style={panelStyle}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 4 }}>
          Taxonomy Governance
        </div>
        <div style={{ color: "#4b5563", fontSize: 12, marginBottom: 10 }}>
          Govern canonical leaves before deterministic certain and deterministic trusted rules can lock them.
        </div>
        {configPath ? (
          <div style={{ color: "#6b7280", fontSize: 12, marginBottom: 10 }}>Source: {configPath}</div>
        ) : null}

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <SummaryTile label="Categories" value={summary.categories} />
          <SummaryTile label="Attributes" value={summary.attributes} />
          <SummaryTile label="Governable leaves" value={summary.governable_leaves} />
          <SummaryTile label="Active" value={summary.active} />
          <SummaryTile label="Needs review" value={summary.needs_review} />
          <SummaryTile label="Deprecated" value={summary.deprecated} />
          <SummaryTile label="Changed" value={summary.changed} />
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
        <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 8 }}>Leaf editor</div>

        <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
          <div style={subPanelStyle}>
            <div style={{ fontSize: 12, marginBottom: 4, color: "#6b7280" }}>Category</div>
            <select
              value={selectedCategoryKey}
              onChange={(event) => setSelectedCategoryKey(event.target.value)}
              style={inputStyle}
            >
              {categoryOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div style={subPanelStyle}>
            <div style={{ fontSize: 12, marginBottom: 4, color: "#6b7280" }}>Attribute</div>
            <select
              value={selectedAttributeId}
              onChange={(event) => setSelectedAttributeId(event.target.value)}
              style={inputStyle}
            >
              {attributeOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div style={subPanelStyle}>
            <div style={{ fontSize: 12, marginBottom: 4, color: "#6b7280" }}>Leaf</div>
            <select
              value={selectedLeafId}
              onChange={(event) => setSelectedLeafId(event.target.value)}
              style={inputStyle}
            >
              {leafOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {selectedRow ? (
          <div style={{ marginTop: 10, display: "grid", gap: 10, gridTemplateColumns: "minmax(280px, 1.1fr) minmax(320px, 1.4fr)" }}>
            <div style={subPanelStyle}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 8 }}>Selected leaf</div>
              <div style={{ display: "grid", gap: 8 }}>
                <div>
                  <div style={{ fontSize: 12, color: "#6b7280" }}>Path</div>
                  <div style={{ color: "#111827", fontWeight: 600 }}>
                    {selectedRow.category_key} / {selectedRow.attribute_id} / {selectedRow.leaf_id}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: "#6b7280" }}>Label</div>
                  <div style={{ color: "#111827" }}>{selectedRow.label || selectedRow.leaf_id}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>Current status</div>
                  {statusBadge(selectedRow.status)}
                </div>
                <div>
                  <div style={{ fontSize: 12, color: "#6b7280" }}>Current action</div>
                  <div style={{ color: "#111827" }}>{selectedRow.governance_action || "none"}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: "#6b7280" }}>Current successors</div>
                  <div style={{ color: "#111827" }}>
                    {(selectedRow.successor_leaf_ids || []).length
                      ? selectedRow.successor_leaf_ids.join(", ")
                      : "none"}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: "#6b7280" }}>Governance state</div>
                  <div style={{ color: "#111827" }}>{selectedChangeState ? "Changed from runtime default" : "Clean / active"}</div>
                </div>
              </div>
            </div>

            <div style={subPanelStyle}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 8 }}>Governance action</div>
              <div style={{ color: "#4b5563", fontSize: 12, marginBottom: 8 }}>
                Choose the business action first. The underlying status and remap fields are set automatically.
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                  type="button"
                  onClick={() => setLeafWorkflow("active")}
                  style={{
                    ...buttonStyle,
                    background: selectedWorkflow === "active" ? "#111827" : "#fff",
                    color: selectedWorkflow === "active" ? "#fff" : "#111827",
                  }}
                >
                  Keep active
                </button>
                <button
                  type="button"
                  onClick={() => setLeafWorkflow("needs_review")}
                  style={{
                    ...buttonStyle,
                    background: selectedWorkflow === "needs_review" ? "#111827" : "#fff",
                    color: selectedWorkflow === "needs_review" ? "#fff" : "#111827",
                  }}
                >
                  Needs review
                </button>
                <button
                  type="button"
                  onClick={() => setLeafWorkflow("merge")}
                  style={{
                    ...buttonStyle,
                    background: selectedWorkflow === "merge" ? "#111827" : "#fff",
                    color: selectedWorkflow === "merge" ? "#fff" : "#111827",
                  }}
                >
                  Merge into…
                </button>
                <button
                  type="button"
                  onClick={() => setLeafWorkflow("split")}
                  disabled={selectedAttributeSelection !== "multi"}
                  style={{
                    ...buttonStyle,
                    background: selectedWorkflow === "split" ? "#111827" : "#fff",
                    color: selectedWorkflow === "split" ? "#fff" : "#111827",
                    opacity: selectedAttributeSelection !== "multi" ? 0.5 : 1,
                    cursor: selectedAttributeSelection !== "multi" ? "not-allowed" : "pointer",
                  }}
                >
                  Split into…
                </button>
                <button
                  type="button"
                  onClick={() => setLeafWorkflow("draft")}
                  style={{
                    ...buttonStyle,
                    background: selectedWorkflow === "draft" ? "#111827" : "#fff",
                    color: selectedWorkflow === "draft" ? "#fff" : "#111827",
                  }}
                >
                  Mark draft
                </button>
              </div>

              <div style={{ marginTop: 10, color: "#111827", fontSize: 12 }}>
                {selectedWorkflow === "active"
                  ? "This leaf will remain active and lockable."
                  : selectedWorkflow === "needs_review"
                    ? "This leaf will be held out of runtime until the taxonomy decision is made."
                    : selectedWorkflow === "draft"
                      ? "This leaf will stay draft-only and out of runtime."
                      : selectedWorkflow === "merge"
                        ? "This leaf will be deprecated and remapped into one canonical successor."
                        : "This leaf will be deprecated and split into multiple successor leaves."}
              </div>

              {selectedAttributeSelection !== "multi" ? (
                <div style={{ marginTop: 8, color: "#6b7280", fontSize: 12 }}>
                  Split is disabled because this attribute is `selection=single`.
                </div>
              ) : null}

              <div style={{ marginTop: 8 }}>
                <div style={{ fontSize: 12, marginBottom: 6, color: "#6b7280" }}>
                  {editorAction === "merge"
                    ? "Choose one successor leaf"
                    : editorAction === "split"
                      ? "Choose successor leaves"
                      : "Successor leaves"}
                </div>
                {successorOptions.length ? (
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {successorOptions.map((option) => {
                      const selected = editorSuccessorLeafIds.includes(option.value);
                      return (
                        <button
                          key={option.value}
                          type="button"
                          disabled={editorStatus === "active" || !editorAction}
                          onClick={() => {
                            if (!editorAction) {
                              return;
                            }
                            if (editorAction === "merge") {
                              setEditorSuccessorLeafIds(selected ? [] : [option.value]);
                              return;
                            }
                            const nextValues = selected
                              ? editorSuccessorLeafIds.filter((value) => value !== option.value)
                              : [...editorSuccessorLeafIds, option.value];
                            setEditorSuccessorLeafIds(nextValues);
                          }}
                          style={{
                            ...buttonStyle,
                            background: selected ? "#111827" : "#fff",
                            color: selected ? "#fff" : "#111827",
                            opacity: editorStatus === "active" || !editorAction ? 0.5 : 1,
                          }}
                        >
                          {option.label}
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div style={{ color: "#6b7280", fontSize: 12 }}>No sibling leaves available.</div>
                )}
              </div>

              <div style={{ marginTop: 8 }}>
                <div style={{ fontSize: 12, marginBottom: 4, color: "#6b7280" }}>Reason</div>
                <textarea
                  value={editorReason}
                  onChange={(event) => setEditorReason(event.target.value)}
                  placeholder="Explain why the leaf is being held, merged, split, or kept as draft"
                  style={{
                    ...inputStyle,
                    minHeight: 100,
                    resize: "vertical",
                    fontFamily: 'inherit',
                  }}
                />
              </div>

              <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button type="button" onClick={applySelectedLeaf} style={primaryButtonStyle}>
                  Apply leaf changes
                </button>
                <button type="button" onClick={resetSelectedLeafForm} style={buttonStyle}>
                  Reset form
                </button>
                <button type="button" onClick={clearSelectedLeafGovernance} style={buttonStyle}>
                  Clear governance
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div style={{ ...subPanelStyle, marginTop: 10, color: "#6b7280" }}>
            No governable leaves are available in the current draft.
          </div>
        )}
      </div>

      <div style={panelStyle}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 8 }}>Governed leaves</div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 10 }}>
          <div style={{ ...subPanelStyle, minWidth: 220, flex: "1 1 220px" }}>
            <div style={{ fontSize: 12, marginBottom: 4, color: "#6b7280" }}>Status scope</div>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              style={inputStyle}
            >
              <option value="changed">Changed only</option>
              <option value="all">All</option>
              <option value="active">Active</option>
              <option value="draft">Draft</option>
              <option value="needs_review">Needs review</option>
              <option value="deprecated">Deprecated</option>
            </select>
          </div>

          <div style={{ ...subPanelStyle, minWidth: 260, flex: "1 1 260px" }}>
            <div style={{ fontSize: 12, marginBottom: 4, color: "#6b7280" }}>Search</div>
            <input
              style={inputStyle}
              value={searchFilter}
              onChange={(event) => setSearchFilter(event.target.value)}
              placeholder="category / attribute / leaf / reason"
            />
          </div>
        </div>

        {visibleRows.length ? (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr>
                  {["Category", "Attribute", "Leaf", "Status", "Action", "Successors", "Reason"].map((label) => (
                    <th
                      key={label}
                      style={{
                        textAlign: "left",
                        padding: "8px 6px",
                        borderBottom: "1px solid #e5e7eb",
                        color: "#374151",
                        background: "#f9fafb",
                        fontWeight: 600,
                      }}
                    >
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibleRows.slice(0, 300).map((row) => {
                  const isSelected =
                    row.category_key === selectedCategoryKey &&
                    row.attribute_id === selectedAttributeId &&
                    row.leaf_id === selectedLeafId;
                  return (
                    <tr
                      key={`${row.category_key}.${row.attribute_id}.${row.leaf_id}`}
                      onClick={() => {
                        setSelectedCategoryKey(row.category_key);
                        setSelectedAttributeId(row.attribute_id);
                        setSelectedLeafId(row.leaf_id);
                      }}
                      style={{
                        cursor: "pointer",
                        background: isSelected ? "#f3f4f6" : "transparent",
                      }}
                    >
                      <td style={{ padding: "8px 6px", borderBottom: "1px solid #f3f4f6" }}>{row.category_key}</td>
                      <td style={{ padding: "8px 6px", borderBottom: "1px solid #f3f4f6" }}>{row.attribute_id}</td>
                      <td style={{ padding: "8px 6px", borderBottom: "1px solid #f3f4f6" }}>{row.label || row.leaf_id}</td>
                      <td style={{ padding: "8px 6px", borderBottom: "1px solid #f3f4f6" }}>{statusBadge(row.status)}</td>
                      <td style={{ padding: "8px 6px", borderBottom: "1px solid #f3f4f6" }}>{row.governance_action || ""}</td>
                      <td style={{ padding: "8px 6px", borderBottom: "1px solid #f3f4f6" }}>{(row.successor_leaf_ids || []).join(", ")}</td>
                      <td style={{ padding: "8px 6px", borderBottom: "1px solid #f3f4f6" }}>{row.governance_reason || ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ ...subPanelStyle, textAlign: "center", color: "#6b7280" }}>
            No leaves match the current filters.
          </div>
        )}
      </div>

      <div style={panelStyle}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 8 }}>Validate & publish</div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 10 }}>
          <div style={{ ...subPanelStyle, minWidth: 180, flex: "1 1 180px" }}>
            <div style={{ fontSize: 12, marginBottom: 4, color: "#6b7280" }}>Actor</div>
            <input
              style={inputStyle}
              value={publishActor}
              onChange={(event) => setPublishActor(event.target.value)}
              placeholder="publish actor"
            />
          </div>

          <div style={{ ...subPanelStyle, minWidth: 180, flex: "1 1 180px" }}>
            <div style={{ fontSize: 12, marginBottom: 4, color: "#6b7280" }}>Version override</div>
            <input
              style={inputStyle}
              value={publishVersion}
              onChange={(event) => setPublishVersion(event.target.value)}
              placeholder="optional version"
            />
          </div>

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
          <button type="button" onClick={previewConfig} style={buttonStyle}>
            Preview publish impact
          </button>
          <button
            type="button"
            onClick={applyNormalizedConfig}
            style={buttonStyle}
            disabled={!validation || !validation.valid || !validation.normalized_config}
          >
            Apply normalized
          </button>
          <button
            type="button"
            onClick={publishConfig}
            style={primaryButtonStyle}
            disabled={
              requiresExplicitRuleAcknowledgement && !acknowledgeInvalidExplicitRules
            }
          >
            Publish
          </button>
          <button type="button" onClick={loadConfig} style={buttonStyle}>
            Reload published
          </button>
        </div>

        {validation ? (
          <div style={{ display: "grid", gap: 8 }}>
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

        {preview ? (
          <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "#111827" }}>
              Publish preview: {preview.valid ? "READY" : "BLOCKED"}
            </div>

            {preview.warnings && preview.warnings.length ? (
              <div style={{ border: "1px solid #fde68a", background: "#fffbeb", borderRadius: 8, padding: 10 }}>
                <div style={{ fontWeight: 600, color: "#92400e", marginBottom: 6, fontSize: 12 }}>Preview warnings</div>
                <ul style={{ margin: 0, paddingLeft: 20, color: "#92400e", fontSize: 12 }}>
                  {preview.warnings.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {preview.errors && preview.errors.length ? (
              <div style={{ border: "1px solid #fecaca", background: "#fef2f2", borderRadius: 8, padding: 10 }}>
                <div style={{ fontWeight: 600, color: "#991b1b", marginBottom: 6, fontSize: 12 }}>Preview errors</div>
                <ul style={{ margin: 0, paddingLeft: 20, color: "#991b1b", fontSize: 12 }}>
                  {preview.errors.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {preview.explicit_rule_summary ? (
              <div style={{ display: "grid", gap: 10 }}>
                <div style={{ color: "#4b5563", fontSize: 12 }}>
                  Explicit rules source: {preview.explicit_rules_path}
                </div>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <SummaryTile
                    label="Newly invalid rules"
                    value={preview.explicit_rule_summary?.newly_invalid_rules || 0}
                  />
                  <SummaryTile
                    label="Newly invalid active rules"
                    value={preview.explicit_rule_summary?.newly_invalid_active_rules || 0}
                  />
                  <SummaryTile
                    label="Draft invalid rules"
                    value={preview.explicit_rule_summary?.draft_invalid_rules || 0}
                  />
                  <SummaryTile
                    label="Current invalid rules"
                    value={preview.explicit_rule_summary?.current_invalid_rules || 0}
                  />
                </div>

                {preview.explicit_rule_impacts && preview.explicit_rule_impacts.length ? (
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                      <thead>
                        <tr>
                          {["Rule", "Category", "Attribute", "Value", "Reason", "Taxonomy status", "Rule status"].map((label) => (
                            <th
                              key={label}
                              style={{
                                textAlign: "left",
                                padding: "8px 6px",
                                borderBottom: "1px solid #e5e7eb",
                                color: "#374151",
                                background: "#f9fafb",
                                fontWeight: 600,
                              }}
                            >
                              {label}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {preview.explicit_rule_impacts.slice(0, 200).map((item) => (
                          <tr key={`${item.rule_id}.${item.reason}`}>
                            <td style={{ padding: "8px 6px", borderBottom: "1px solid #f3f4f6" }}>{item.rule_id}</td>
                            <td style={{ padding: "8px 6px", borderBottom: "1px solid #f3f4f6" }}>{item.category_key}</td>
                            <td style={{ padding: "8px 6px", borderBottom: "1px solid #f3f4f6" }}>{item.attribute_id}</td>
                            <td style={{ padding: "8px 6px", borderBottom: "1px solid #f3f4f6" }}>
                              {item.value_label || item.value_key}
                            </td>
                            <td style={{ padding: "8px 6px", borderBottom: "1px solid #f3f4f6" }}>{formatImpactReason(item.reason)}</td>
                            <td style={{ padding: "8px 6px", borderBottom: "1px solid #f3f4f6" }}>{item.taxonomy_status || ""}</td>
                            <td style={{ padding: "8px 6px", borderBottom: "1px solid #f3f4f6" }}>{item.signal_status || ""}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div style={{ ...subPanelStyle, textAlign: "center", color: "#166534" }}>
                    No explicit rules are newly invalid under this draft taxonomy.
                  </div>
                )}

                {(preview.explicit_rule_summary?.newly_invalid_active_rules || 0) > 0 ? (
                  <label
                    style={{
                      display: "flex",
                      gap: 8,
                      alignItems: "flex-start",
                      padding: 10,
                      border: "1px solid #fde68a",
                      borderRadius: 8,
                      background: "#fffbeb",
                      color: "#92400e",
                      fontSize: 12,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={acknowledgeInvalidExplicitRules}
                      onChange={(event) => setAcknowledgeInvalidExplicitRules(event.target.checked)}
                      style={{ marginTop: 2 }}
                    />
                    <span>
                      I understand that publishing this taxonomy will invalidate active explicit rules and I want to proceed.
                    </span>
                  </label>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      <details style={panelStyle}>
        <summary style={{ cursor: "pointer", fontSize: 12, fontWeight: 600, color: "#111827" }}>
          Advanced JSON snapshot
        </summary>
        <div style={{ color: "#6b7280", fontSize: 12, marginTop: 10, marginBottom: 8 }}>
          Read-only debug view of the current draft. Normal editing should happen through the leaf editor above.
        </div>
        <textarea
          value={jsonSnapshot}
          readOnly
          style={{
            width: "100%",
            minHeight: 300,
            fontFamily: '"SFMono-Regular", Menlo, monospace',
            fontSize: 12,
            border: "1px solid #d1d5db",
            borderRadius: 8,
            padding: 10,
            background: "#f9fafb",
          }}
        />
      </details>

      <div style={panelStyle}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 8 }}>Audit & versions</div>

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
                { key: "actor", label: "Actor" },
              ],
              auditRows.slice(0, 15),
              "audit"
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

ReactDOM.render(<App />, document.getElementById("reactTaxonomyGovernanceApp"));

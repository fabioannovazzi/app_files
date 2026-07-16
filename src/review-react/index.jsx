import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom";

const apiBase = `${window.location.origin.replace(/\/$/, "")}/review`;
const ALL_VALUE = "__all__";
const HYBRID_VALUE_LABELS = {
  yes: "Yes",
  no: "No",
};

function hybridFilterLabel(key) {
  const normalized = String(key || "").trim().toLowerCase();
  if (!normalized || !normalized.startsWith("also_")) return "Hybrid";
  const suffix = normalized.slice("also_".length).replace(/_/g, " ").trim();
  if (!suffix) return "Hybrid";
  return `Also ${suffix}`;
}

function isHybridColumnKey(key) {
  const text = String(key || "").trim().toLowerCase();
  if (!text) return false;
  if (/^also_[a-z0-9_]+$/.test(text)) return true;
  if (/^also_[a-z0-9_]+_(secondary_category|source|evidence)$/.test(text)) return true;
  if (/^brand_claims_[a-z0-9_]+_hybrid$/.test(text)) return true;
  if (/^inferred_[a-z0-9_]+_hybrid$/.test(text)) return true;
  return false;
}

function isHybridFlagColumnKey(key) {
  const text = String(key || "").trim().toLowerCase();
  if (!text.startsWith("also_")) return false;
  if (/_(secondary_category|source|evidence)$/.test(text)) return false;
  return true;
}

function SegmentedButton({ label, active, onClick, tooltip }) {
  const [hover, setHover] = useState(false);
  const style = {
    border: "1px solid #e5e7eb",
    borderRadius: 999,
    padding: "6px 10px",
    background: active ? "#111827" : "#fff",
    color: active ? "#fff" : "#111827",
    cursor: active ? "default" : "pointer",
    position: "relative",
  };
  return (
    <span style={{ position: "relative", display: "inline-block" }}>
      <button
        type="button"
        aria-pressed={active}
        onClick={active ? undefined : onClick}
        style={style}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
      >
        {label}
      </button>
      {hover && (
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
      )}
    </span>
  );
}

const sanitizeUrl = (url) => {
  if (!url) return null;
  let cleaned = String(url).trim();
  cleaned = cleaned.replace(/\\u002F/gi, "/").replace(/\\\//g, "/");
  return cleaned || null;
};

const buildCsvFilename = ({ recordType, categories, retailers }) => {
  const selectedCategories = Array.from(categories || []);
  let categoryPart = "all";
  if (selectedCategories.length === 1) {
    categoryPart = selectedCategories[0];
  } else if (selectedCategories.length > 1) {
    categoryPart = `${selectedCategories[0]}_plus${selectedCategories.length - 1}`;
  }
  const selectedRetailers = Array.from(retailers || []);
  let retailerPart = "all";
  if (selectedRetailers.length === 1 && selectedRetailers[0] !== ALL_VALUE) {
    retailerPart = selectedRetailers[0];
  } else if (selectedRetailers.length > 1) {
    retailerPart = `${selectedRetailers[0]}_plus${selectedRetailers.length - 1}`;
  }
  const recordLabel = recordType === "variant" ? "variants" : "parents";
  return `pdp_${recordLabel}_${categoryPart}_${retailerPart}.csv`;
};

function useFetchJson(url, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(url, { credentials: "include" })
      .then((resp) => {
        if (!resp.ok) {
          throw new Error(`Request failed (${resp.status})`);
        }
        return resp.json();
      })
      .then((json) => {
        if (!cancelled) setData(json);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, deps);

  return { data, loading, error };
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
      if (next.size === 0 && allowAll) {
        next.add(ALL_VALUE);
      }
    }
    onChange(next);
  };
  if (!options.length) {
    return <span style={{ color: "#9ca3af" }}>No options</span>;
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
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

function ViewToggle({ active = "catalog" }) {
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

function Filters({
  retailers,
  categories,
  brandOptions,
  priceBandOptions,
  hybridFilterOptions,
  state,
  setState,
  total,
}) {
  const update = (patch) => setState((s) => ({ ...s, ...patch }));
  const maxLimit = Math.max(1, Math.min(200, typeof total === "number" ? total : 200));

  const Card = ({ title, children, fitContent = false }) => (
    <div
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: 12,
        padding: 12,
        background: "#fff",
        minWidth: 260,
        width: fitContent ? "fit-content" : "auto",
        maxWidth: "100%",
      }}
    >
      {title ? (
        <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 8 }}>{title}</div>
      ) : null}
      {children}
    </div>
  );

  return (
    <div style={{ display: "flex", gap: 16, marginBottom: 16, flexWrap: "wrap", alignItems: "flex-start" }}>
      <Card title="Settings" fitContent>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <div
            style={{
              border: "1px solid #e5e7eb",
              borderRadius: 10,
              padding: 10,
              background: "#f9fafb",
            }}
          >
            <ViewToggle active="catalog" />
          </div>
          <div
            style={{
              border: "1px solid #e5e7eb",
              borderRadius: 10,
              padding: 10,
              background: "#f9fafb",
              minWidth: 140,
            }}
          >
            <PillGroup
              options={[
                { value: "parent", label: "parent" },
                { value: "variant", label: "variant" },
              ]}
              selectedValues={new Set([state.recordType])}
              allowAll={false}
              single
              onChange={(vals) => {
                const [next] = Array.from(vals);
                if (next) setState((s) => ({ ...s, recordType: next }));
              }}
            />
          </div>
          <div
            style={{
              border: "1px solid #e5e7eb",
              borderRadius: 10,
              padding: 10,
              background: "#f9fafb",
              minWidth: 220,
            }}
          >
            <div style={{ fontSize: 12, marginBottom: 2 }}>Displayed items: {state.limit}</div>
            <input
              type="range"
              min="1"
              max={maxLimit}
              value={state.limit}
              onChange={(e) => setState((s) => ({ ...s, limit: Number(e.target.value) }))}
              style={{ width: "100%" }}
            />
          </div>
        </div>
      </Card>
      <Card title="Filters">
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <div
            style={{
              border: "1px solid #e5e7eb",
              borderRadius: 10,
              padding: 10,
              background: "#f9fafb",
            }}
          >
            <div style={{ fontSize: 12, marginBottom: 4 }}>Sources</div>
            <PillGroup
              options={retailers.map((r) => ({ value: r, label: r }))}
              selectedValues={state.retailers}
              allowAll={false}
              onChange={(vals) => update({ retailers: vals })}
            />
          </div>
          <div
            style={{
              border: "1px solid #e5e7eb",
              borderRadius: 10,
              padding: 10,
              background: "#f9fafb",
            }}
          >
            <div style={{ fontSize: 12, marginBottom: 4 }}>Categories</div>
            <PillGroup
              options={categories.map((c) => ({ value: c.key, label: c.label }))}
              selectedValues={state.categories}
              allowAll={false}
              onChange={(vals) => update({ categories: vals })}
            />
          </div>
          <div
            style={{
              border: "1px solid #e5e7eb",
              borderRadius: 10,
              padding: 10,
              background: "#f9fafb",
            }}
          >
            <div style={{ fontSize: 12, marginBottom: 4 }}>Brands</div>
            <PillGroup
              options={brandOptions}
              selectedValues={state.brands}
              allowAll={true}
              onChange={(vals) => update({ brands: vals })}
            />
          </div>
          <div
            style={{
              border: "1px solid #e5e7eb",
              borderRadius: 10,
              padding: 10,
              background: "#f9fafb",
            }}
          >
            <div style={{ fontSize: 12, marginBottom: 4 }}>Price bands</div>
            <PillGroup
              options={priceBandOptions}
              selectedValues={state.priceBands}
              allowAll={false}
              onChange={(vals) => update({ priceBands: vals })}
            />
          </div>
          {hybridFilterOptions.map((hybridFilter) => (
            <div
              key={hybridFilter.key}
              style={{
                border: "1px solid #e5e7eb",
                borderRadius: 10,
                padding: 10,
                background: "#f9fafb",
              }}
            >
              <div style={{ fontSize: 12, marginBottom: 4 }}>{hybridFilter.label}</div>
              <PillGroup
                options={[
                  { value: "all", label: "All" },
                  ...hybridFilter.options,
                ]}
                selectedValues={new Set([
                  (state.hybridFilters && state.hybridFilters.get(hybridFilter.key)) || "all",
                ])}
                allowAll={false}
                single
                onChange={(vals) => {
                  const [next] = Array.from(vals);
                  if (!next) return;
                  setState((s) => {
                    const nextMap = new Map(s.hybridFilters || new Map());
                    if (next === "all") {
                      nextMap.delete(hybridFilter.key);
                    } else {
                      nextMap.set(hybridFilter.key, next);
                    }
                    return { ...s, hybridFilters: nextMap };
                  });
                }}
              />
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function Records({
  records,
  attributeColumns = new Set(),
  attributes = [],
  recordType = "parent",
  categories = new Set(),
  retailers = new Set(),
  fetchAllRecords,
}) {
  if (!records || !records.length) {
    return <div>No records.</div>;
  }

  const EXCLUDE_FIELDS = new Set([
    "product_name",
    "brand",
    "category_label",
    "retailer",
    "category_key",
    "category_id",
    "product",
    "parent_product_id",
    "variant",
    "variant_id",
    "raw_category_path",
    "description",
    "variant_description",
    "pdp_url",
    "hero_image_url",
    "swatch_image_url",
  ]);

  const renderValue = (val) => {
    if (val === null || val === undefined) return "—";
    const text = String(val);
    if (text.length > 120) {
      return text.slice(0, 120) + "…";
    }
    return text;
  };

  const resolveColumns = () => {
    const attributeColumnsFromMetadata = Array.isArray(attributes)
      ? attributes
          .map((attr) => (attr && attr.column ? attr.column : null))
          .filter((col) => typeof col === "string" && col.trim())
      : [];
    if (attributeColumnsFromMetadata.length > 0) {
      return attributeColumnsFromMetadata.filter(
        (k) => !EXCLUDE_FIELDS.has(k) && !isHybridColumnKey(k),
      );
    }
    if (attributeColumns && attributeColumns.size > 0) {
      return Array.from(attributeColumns).filter(
        (k) => !EXCLUDE_FIELDS.has(k) && !isHybridColumnKey(k),
      );
    }
    return [];
  };

  const displayKeys = React.useMemo(() => resolveColumns(), [attributeColumns, attributes]);
  const hasValue = (value) => {
    if (value === null || value === undefined) return false;
    if (typeof value === "string") return value.trim() !== "";
    if (Array.isArray(value)) return value.length > 0;
    return true;
  };

  const downloadCsv = async () => {
    let exportRecords = records;
    if (fetchAllRecords) {
      try {
        const allRecords = await fetchAllRecords();
        if (Array.isArray(allRecords) && allRecords.length) {
          exportRecords = allRecords;
        }
      } catch (error) {
        // Fall back to currently loaded records if download fetch fails.
      }
    }
    if (!exportRecords.length) return;
    const hasValue = (value) => {
      if (value === null || value === undefined) return false;
      if (typeof value === "string") return value.trim() !== "";
      if (Array.isArray(value)) return value.length > 0;
      return true;
    };
    const escape = (val) => {
      if (val === null || val === undefined) return "";
      const text = String(val);
      if (/[",\r\n]/.test(text)) {
        return `"${text.replace(/"/g, '""')}"`;
      }
      return text;
    };
    const disallowedVariantKeys = new Set([
      "sample_variant_id",
      "price_raw",
      "currency",
      "availability",
      "variant_key",
      "shade_name",
      "shade_name_id",
      "brand_norm",
      "canonical_accept",
      "canonical_id",
      "product_name_norm",
    ]);
    const baseColumns = [
      { key: "retailer", header: "source" },
      { key: "parent_product_id", header: "parent_product_id" },
      { key: "brand", header: "brand" },
      { key: "product_name", header: "product" },
      { key: "category_label", header: "category" },
      { key: "record_type", header: "record_type" },
      ...(recordType === "parent" ? [{ key: "sample_variant_id", header: "sample_variant_id" }] : []),
    ];
    const optionalColumns =
      recordType === "parent"
        ? [
            { key: "price_raw", header: "price" },
            { key: "currency", header: "currency" },
            { key: "availability", header: "availability" },
          ].filter(({ key }) => exportRecords.some((rec) => hasValue(rec[key])))
        : [];
    const variantColumns =
      recordType === "variant"
        ? [
            { key: "variant_description", header: "variant name" },
            { key: "variant_id", header: "variant_id" },
          ].filter(({ key }) => exportRecords.some((rec) => hasValue(rec[key])))
        : [];
    const reservedKeys = new Set([...baseColumns, ...optionalColumns, ...variantColumns].map((col) => col.key));
    const attributeCandidates =
      attributeColumns && attributeColumns.size > 0 ? Array.from(attributeColumns) : resolveColumns();
    const attributeCols = attributeCandidates
      .filter((col) => !reservedKeys.has(col))
      .filter((col) => !(recordType === "variant" && disallowedVariantKeys.has(col)))
      .filter((col) => exportRecords.some((rec) => hasValue(rec[col])));
    const header = [...baseColumns, ...optionalColumns, ...variantColumns].map((col) => col.header);
    const headerRow = [...header, ...attributeCols].map(escape).join(",");
    const rows = exportRecords.map((rec) => {
      const baseValues = baseColumns.map(({ key }) => {
        if (key === "record_type") {
          return escape(rec.record_type || recordType);
        }
        if (key === "product_name") {
          return escape(rec.product_name || rec.product || rec.parent_product_id || rec.parent || "");
        }
        if (key === "category_label") {
          return escape(rec.category_label || rec.category || "");
        }
        return escape(rec[key]);
      });
      const optionalValues = optionalColumns.map(({ key }) => escape(rec[key]));
      const variantValues =
        recordType === "variant"
          ? variantColumns.map(({ key }) => {
              if (key === "variant_description") {
                return escape(rec.variant_description || rec.variant || rec.variant_id || "");
              }
              return escape(rec[key]);
            })
          : [];
      const attributeValues = attributeCols.map((col) => escape(rec[col]));
      return [...baseValues, ...optionalValues, ...variantValues, ...attributeValues].join(",");
    });
    const csv = "\uFEFF" + [headerRow, ...rows].join("\r\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = buildCsvFilename({ recordType, categories, retailers });
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
        <button
          type="button"
          onClick={downloadCsv}
          style={{
            padding: "6px 10px",
            borderRadius: 6,
            border: "1px solid #e5e7eb",
            background: "#fff",
            color: "#111827",
            cursor: "pointer",
          }}
        >
          Download CSV
        </button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "12px" }}>
        {records.map((rec, idx) => (
          <div key={idx} style={{ border: "1px solid #e5e7eb", borderRadius: 8, padding: 12, background: "#fff" }}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>
              {(() => {
                const baseTitle =
                  rec.product_name ||
                  rec.product ||
                  rec.parent_product_id ||
                  rec.parent ||
                  "Product";
                const variant = rec.variant_description || rec.variant || rec.variant_id;
                const titleText = recordType === "variant" && variant ? `${baseTitle} — ${variant}` : baseTitle;
                const pdpUrl = typeof rec.pdp_url === "string" ? rec.pdp_url.trim() : "";
                if (!pdpUrl) {
                  return titleText;
                }
                return (
                  <a
                    href={pdpUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: "inherit", textDecoration: "underline" }}
                  >
                    {titleText}
                  </a>
                );
              })()}
            </div>
            <div style={{ color: "#4b5563", fontSize: 13, marginBottom: 8 }}>
              {[rec.brand, rec.category_label, rec.retailer].filter(Boolean).join(" · ")}
            </div>
            {Object.entries(rec || {})
              .filter(([key, value]) => isHybridFlagColumnKey(key) && Boolean(value))
              .map(([key]) => {
                const evidenceKey = `${key}_evidence`;
                const evidence = rec[evidenceKey];
                return (
                  <div
                    key={key}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                      fontSize: 12,
                      fontWeight: 600,
                      color: "#0f172a",
                      background: "#fee2e2",
                      border: "1px solid #fecaca",
                      borderRadius: 999,
                      padding: "2px 8px",
                      marginBottom: 8,
                      marginRight: 6,
                    }}
                    title={String(evidence || "Explicit hybrid claim")}
                  >
                    Hybrid: {hybridFilterLabel(key).toLowerCase()}
                  </div>
                );
              })}
            {(() => {
              const hero = sanitizeUrl(rec.hero_image_url);
              const swatch = sanitizeUrl(rec.swatch_image_url);
              const parentId = rec.parent_product_id || rec.product || rec.parent;
              const variantId = rec.variant_id || rec.variant;
              let imgUrl = hero || swatch;
              if (!imgUrl && parentId) {
                const params = new URLSearchParams();
                if (variantId) params.append("variant", variantId);
                imgUrl = `${apiBase}/images/${parentId}${params.toString() ? "?" + params.toString() : ""}`;
              }
              if (!imgUrl) return null;
              return (
                <div style={{ marginBottom: 8 }}>
                  <img src={imgUrl} alt="" style={{ width: "100%", borderRadius: 6, objectFit: "cover" }} />
                </div>
              );
            })()}
            <div style={{ fontSize: 13, color: "#111827" }}>
              {displayKeys
                .filter((k) => hasValue(rec[k]))
                .map((k) => (
                  <div key={k}>
                    <strong>{k}:</strong> {renderValue(rec[k])}
                  </div>
                ))}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function App() {
  const retailersResp = useFetchJson(`${apiBase}/retailers`, []);
  const [categories, setCategories] = useState([]);
  const [brands, setBrands] = useState([]);
  const [records, setRecords] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [attributeColumns, setAttributeColumns] = useState(new Set());
  const [attributes, setAttributes] = useState([]);
  const [priceBandOptionsData, setPriceBandOptionsData] = useState([]);
  const [hybridValuesByKey, setHybridValuesByKey] = useState({});
  const [attributeSelections, setAttributeSelections] = useState(new Map());

  const [state, setState] = useState({
    retailers: new Set(),
    categories: new Set(),
    brands: new Set([ALL_VALUE]),
    priceBands: new Set(),
    hybridFilters: new Map(),
    recordType: "parent",
    limit: 24,
  });

  useEffect(() => {
    if (retailersResp.data && retailersResp.data.retailers && retailersResp.data.retailers.length) {
      const preferred = retailersResp.data.retailers.find(
        (r) => typeof r === "string" && r.toLowerCase() === "ulta",
      );
      const initial = preferred || retailersResp.data.retailers[0];
      setState((s) => ({ ...s, retailers: new Set([initial]) }));
    }
  }, [retailersResp.data]);

  useEffect(() => {
    if (!state.retailers.size) return;
    const params = new URLSearchParams();
    Array.from(state.retailers).forEach((retailer) => params.append("retailer", retailer));
    fetch(`${apiBase}/categories?${params.toString()}`, { credentials: "include" })
      .then((resp) => {
        if (!resp.ok) throw new Error(`Categories failed (${resp.status})`);
        return resp.json();
      })
      .then((json) => {
        setCategories(json.categories || []);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [state.retailers]);

  useEffect(() => {
    setState((s) => {
      if (!categories.length) {
        return s.categories.size ? { ...s, categories: new Set() } : s;
      }
      const available = new Set(categories.map((c) => c.key));
      const kept = new Set(Array.from(s.categories).filter((val) => available.has(val)));
      if (!kept.size) {
        kept.add(categories[0].key);
      }
      const unchanged =
        kept.size === s.categories.size && Array.from(kept).every((val) => s.categories.has(val));
      return unchanged ? s : { ...s, categories: kept };
    });
  }, [categories]);

  useEffect(() => {
    if (!state.retailers.size || !state.categories.size) return;
    const params = new URLSearchParams();
    Array.from(state.retailers).forEach((retailer) => params.append("retailer", retailer));
    Array.from(state.categories).forEach((c) => params.append("category", c));
    fetch(`${apiBase}/brands?${params.toString()}`, { credentials: "include" })
      .then((resp) => {
        if (!resp.ok) throw new Error(`Brands failed (${resp.status})`);
        return resp.json();
      })
      .then((json) => {
        const opts = (json.brands || []).map((b) => ({ value: b, label: b }));
        setBrands([{ value: ALL_VALUE, label: "All" }, ...opts]);
        setState((s) => {
          const current = s.brands || new Set();
          const available = new Set(opts.map((o) => o.value));
          const kept = new Set(
            Array.from(current).filter((val) => val === ALL_VALUE || available.has(val))
          );
          if (kept.size === 0) {
            kept.add(ALL_VALUE);
          }
          return { ...s, brands: kept };
        });
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [state.retailers, state.categories]);

  const buildRecordsParams = React.useCallback(
    (includeLimit = true) => {
      const params = new URLSearchParams();
      if (!state.retailers.size || !state.categories.size) {
        return params;
      }
      Array.from(state.retailers).forEach((retailer) => params.append("retailer", retailer));
      Array.from(state.categories).forEach((c) => params.append("category", c));
      params.append("record_type", state.recordType);
      if (includeLimit) {
        params.append("limit", String(state.limit));
      }
      if (!state.brands.has(ALL_VALUE)) {
        Array.from(state.brands).forEach((b) => params.append("brand", b));
      }
      state.priceBands.forEach((p) => params.append("price_band", p));
      (state.hybridFilters || new Map()).forEach((value, key) => {
        if (value && value !== "all") {
          params.append(key, value);
        }
      });
      attributeSelections.forEach((vals, attrId) => {
        if (vals && vals.size) {
          params.append("filters", `${attrId}:${Array.from(vals).join("|")}`);
        }
      });
      return params;
    },
    [state, attributeSelections],
  );

  const buildFiltersParams = React.useCallback(() => {
    const params = new URLSearchParams();
    if (!state.retailers.size || !state.categories.size) {
      return params;
    }
    Array.from(state.retailers).forEach((retailer) => params.append("retailer", retailer));
    Array.from(state.categories).forEach((c) => params.append("category", c));
    params.append("record_type", state.recordType);
    if (!state.brands.has(ALL_VALUE)) {
      Array.from(state.brands).forEach((b) => params.append("brand", b));
    }
    state.priceBands.forEach((p) => params.append("price_band", p));
    (state.hybridFilters || new Map()).forEach((value, key) => {
      if (value && value !== "all") {
        params.append(key, value);
      }
    });
    attributeSelections.forEach((vals, attrId) => {
      if (vals && vals.size) {
        params.append("filters", `${attrId}:${Array.from(vals).join("|")}`);
      }
    });
    return params;
  }, [state, attributeSelections]);

  const reloadRecords = React.useCallback(() => {
    const params = buildRecordsParams(true);
    if (!params.has("retailer") || !params.has("category")) {
      return;
    }
    setLoading(true);
    setError(null);
    fetch(`${apiBase}/records?${params.toString()}`, { credentials: "include" })
      .then((resp) => {
        if (!resp.ok) throw new Error(`Records failed (${resp.status})`);
        return resp.json();
      })
      .then((json) => {
        setRecords(json.records || []);
        setTotal(json.total || 0);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [buildRecordsParams]);

  const fetchAllRecords = React.useCallback(async () => {
    const params = buildRecordsParams(false);
    if (!params.has("retailer") || !params.has("category")) {
      return [];
    }
    const resp = await fetch(`${apiBase}/records/download?${params.toString()}`, { credentials: "include" });
    if (!resp.ok) {
      throw new Error(`Records download failed (${resp.status})`);
    }
    const json = await resp.json();
    return json.records || [];
  }, [buildRecordsParams]);

  useEffect(() => {
    reloadRecords();
  }, [reloadRecords]);

  useEffect(() => {
    if (typeof total !== "number" || Number.isNaN(total)) {
      return;
    }
    const desired = Math.max(1, Math.min(200, total));
    setState((prev) => (prev.limit === desired ? prev : { ...prev, limit: desired }));
  }, [total]);

  useEffect(() => {
    if (!state.retailers.size || !state.categories.size) {
      setAttributeColumns(new Set());
      setAttributes([]);
      setPriceBandOptionsData([]);
      setHybridValuesByKey({});
      return;
    }
    const params = buildFiltersParams();
    if (!params.has("retailer") || !params.has("category")) {
      setAttributeColumns(new Set());
      setAttributes([]);
      setHybridValuesByKey({});
      return;
    }
    fetch(`${apiBase}/filters?${params.toString()}`, { credentials: "include" })
      .then((resp) => {
        if (!resp.ok) throw new Error(`Filters failed (${resp.status})`);
        return resp.json();
      })
      .then((json) => {
        const attrs = json.attributes || [];
        setAttributeColumns(new Set()); // show/export all attributes seen in records, not just shared category columns
        setAttributes(attrs);
        setPriceBandOptionsData(Array.isArray(json.price_band_values) ? json.price_band_values : []);
        const parsedHybridValues = {};
        const rawHybridValues = json && typeof json.hybrid_values === "object" && json.hybrid_values
          ? json.hybrid_values
          : {};
        Object.entries(rawHybridValues).forEach(([key, values]) => {
          const normalizedValues = Array.isArray(values)
            ? values
              .map((value) => String(value || "").trim().toLowerCase())
              .filter((value) => value === "yes" || value === "no")
            : [];
          const uniqueValues = Array.from(new Set(normalizedValues));
          if (key && uniqueValues.includes("yes")) {
            parsedHybridValues[String(key)] = uniqueValues;
          }
        });
        if (!Object.keys(parsedHybridValues).length && Array.isArray(json.also_blush_values)) {
          const fallbackValues = Array.from(
            new Set(
              json.also_blush_values
                .map((value) => String(value || "").trim().toLowerCase())
                .filter((value) => value === "yes" || value === "no"),
            ),
          );
          if (fallbackValues.includes("yes")) {
            parsedHybridValues.also_blush = fallbackValues;
          }
        }
        setHybridValuesByKey(parsedHybridValues);
      })
      .catch(() => {
        setAttributeColumns(new Set());
        setAttributes([]);
        setPriceBandOptionsData([]);
        setHybridValuesByKey({});
      });
  }, [buildFiltersParams]);

  useEffect(() => {
    // Prune attribute selections to current attribute/value options
    if (!attributes || !attributes.length) {
      if (attributeSelections.size) {
        setAttributeSelections(new Map());
      }
      return;
    }
    const allowed = new Map(
      attributes.map((attr) => {
        const values = new Set((attr.values || []).map((v) => String(v)));
        return [attr.id, values];
      }),
    );
    let changed = false;
    const next = new Map();
    attributeSelections.forEach((vals, attrId) => {
      if (!allowed.has(attrId)) {
        changed = true;
        return;
      }
      const options = allowed.get(attrId);
      const kept = new Set(Array.from(vals || []).filter((val) => options.has(String(val))));
      if (kept.size) {
        next.set(attrId, kept);
      } else if ((vals || new Set()).size) {
        changed = true;
      } else {
        next.set(attrId, kept);
      }
    });
    if (changed) {
      setAttributeSelections(next);
    }
  }, [attributes, attributeSelections]);

  useEffect(() => {
    const availableEntries = Object.entries(hybridValuesByKey || {});
    setState((s) => {
      const current = s.hybridFilters || new Map();
      const next = new Map();
      availableEntries.forEach(([key, values]) => {
        const allowed = new Set(
          (Array.isArray(values) ? values : [])
            .map((value) => String(value || "").trim().toLowerCase())
            .filter((value) => value === "yes" || value === "no"),
        );
        if (!allowed.size) return;
        const selected = String(current.get(key) || "").trim().toLowerCase();
        if (selected && selected !== "all" && allowed.has(selected)) {
          next.set(key, selected);
        }
      });
      const unchanged = next.size === current.size
        && Array.from(next.entries()).every(([key, value]) => current.get(key) === value);
      return unchanged ? s : { ...s, hybridFilters: next };
    });
  }, [hybridValuesByKey]);

  useEffect(() => {
    // Prune price band selections to available options
    if (!priceBandOptionsData || !priceBandOptionsData.length) {
      return;
    }
    const allowed = new Set(priceBandOptionsData);
    const kept = new Set(Array.from(state.priceBands || []).filter((val) => allowed.has(val)));
    if (kept.size !== state.priceBands.size) {
      setState((s) => ({ ...s, priceBands: kept }));
    }
  }, [priceBandOptionsData, state.priceBands.size]);

  const retailerOptions = retailersResp.data?.retailers || [];
  const priceBandOptions =
    priceBandOptionsData && priceBandOptionsData.length
      ? ["premium", "mid", "value"]
          .filter((val) => priceBandOptionsData.includes(val))
          .map((val) => ({ value: val, label: val.charAt(0).toUpperCase() + val.slice(1) }))
      : [
          { value: "premium", label: "Premium" },
          { value: "mid", label: "Mid" },
          { value: "value", label: "Value" },
        ];
  const hybridFilterOptions = React.useMemo(() => (
    Object.entries(hybridValuesByKey || {}).map(([key, values]) => ({
      key,
      label: hybridFilterLabel(key),
      options: (Array.isArray(values) ? values : []).map((value) => ({
        value,
        label: HYBRID_VALUE_LABELS[value] || value,
      })),
    }))
  ), [hybridValuesByKey]);

  return (
    <div>
      {retailersResp.loading && <div>Loading retailers…</div>}
      {retailersResp.error && <div style={{ color: "red" }}>{retailersResp.error}</div>}
      <Filters
        retailers={retailerOptions}
        categories={categories}
        brandOptions={brands}
        priceBandOptions={priceBandOptions}
        hybridFilterOptions={hybridFilterOptions}
        state={state}
        setState={setState}
        total={total}
      />
      <div
        style={{
          border: "1px solid #e5e7eb",
          borderRadius: 12,
          padding: 12,
          background: "#fff",
          marginBottom: 16,
        }}
      >
        <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 8 }}>Attributes</div>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-start" }}>
          {attributes.map((attr) => {
            const selected = attributeSelections.get(attr.id) || new Set();
            const options = (attr.values || []).map((v) => ({ value: v, label: v }));
            return (
              <div
                key={attr.id}
                style={{
                  minWidth: 200,
                  border: "1px solid #e5e7eb",
                  borderRadius: 10,
                  padding: 10,
                  background: "#f9fafb",
                }}
              >
                <div style={{ fontSize: 12, marginBottom: 6 }}>{attr.label || attr.id}</div>
                <PillGroup
                  options={options}
                  selectedValues={selected}
                  allowAll={false}
                  onChange={(vals) => {
                    setAttributeSelections((prev) => {
                      const next = new Map(prev);
                      next.set(attr.id, vals);
                      return next;
                    });
                  }}
                />
              </div>
            );
          })}
        </div>
      </div>
      {error && <div style={{ color: "red" }}>{error}</div>}
      {loading ? (
        <div>Loading records…</div>
      ) : (
        <Records
          records={records}
          attributeColumns={attributeColumns}
          attributes={attributes}
          recordType={state.recordType}
          categories={state.categories}
          retailers={state.retailers}
          fetchAllRecords={fetchAllRecords}
        />
      )}
      {!loading && (
        <div style={{ marginTop: 8, color: "#4b5563", fontSize: 13 }}>
          Showing {records.length} of {total || records.length} ({state.recordType})
        </div>
      )}
    </div>
  );
}

const rootEl = document.getElementById("reactApp");
ReactDOM.createRoot(rootEl).render(<App />);

(() => {
  function buildTranslator(copy, prefix = "") {
    const normalizedPrefix = prefix ? `${prefix}.` : "";
    return function t(path, fallback = "") {
      const effectivePath =
        normalizedPrefix && path.startsWith(normalizedPrefix)
          ? path.slice(normalizedPrefix.length)
          : path;
      return (
        effectivePath.split(".").reduce((acc, key) => {
          if (acc && typeof acc === "object" && key in acc) {
            return acc[key];
          }
          return undefined;
        }, copy) ?? fallback
      );
    };
  }

  function formatTemplate(template, values = {}) {
    if (typeof template !== "string") {
      return "";
    }
    return template.replace(/\{(\w+)\}/g, (_, key) =>
      values[key] !== undefined ? values[key] : ""
    );
  }

  function createApiRequest(apiBase, lang) {
    const base = typeof apiBase === "string" ? apiBase.replace(/\/$/, "") : "";
    return function apiRequest(path, options = {}, expectJson = true) {
      const headers = new Headers(options.headers || {});
      let body = options.body;
      if (body && !(body instanceof FormData) && !(body instanceof Blob)) {
        if (typeof body !== "string") {
          headers.set("Content-Type", "application/json");
          body = JSON.stringify(body);
        } else if (!headers.has("Content-Type")) {
          headers.set("Content-Type", "application/json");
        }
      }
      const url =
        lang && typeof lang === "string" && lang.length
          ? path.includes("?")
            ? `${base}${path}&lang=${lang}`
            : `${base}${path}?lang=${lang}`
          : `${base}${path}`;
      return fetch(url, {
        ...options,
        headers,
        body,
      }).then(async (response) => {
        if (!response.ok) {
          let detail = response.statusText;
          try {
            const payload = await response.json();
            detail = payload.detail ?? payload.message ?? detail;
            if (detail && typeof detail !== "string") {
              detail = JSON.stringify(detail);
            }
          } catch {
            // ignore JSON parse errors
          }
          throw new Error(detail);
        }
        if (!expectJson) {
          return response;
        }
        return response.json();
      });
    };
  }

  function renderTable(element, table) {
    if (!element || !table || !Array.isArray(table.columns) || !Array.isArray(table.rows)) {
      if (element) {
        element.innerHTML = "";
      }
      return;
    }
    const header = table.columns.map((col) => `<th>${col}</th>`).join("");
    const rows = table.rows
      .map((row) => `<tr>${row.map((cell) => `<td>${cell ?? ""}</td>`).join("")}</tr>`)
      .join("");
    element.innerHTML = `<thead><tr>${header}</tr></thead><tbody>${rows}</tbody>`;
  }

  window.buildTranslator = buildTranslator;
  window.formatTemplate = formatTemplate;
  window.createApiRequest = createApiRequest;
  window.renderTable = renderTable;
})();

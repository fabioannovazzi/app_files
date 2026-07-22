import React, { useEffect } from "react";
import { createRoot } from "react-dom/client";

const apiBase = `${window.location.origin.replace(/\/$/, "")}/check`;
const currentLang = window.appLanguage || "en";
const appCopy = window.appCopy || {};
const OCR_LANG_MAP = { it: "ita", fr: "fra", de: "deu", es: "spa" };

function readBootstrap() {
  const node = document.getElementById("checkEntriesBootstrap");
  if (!node) {
    return {};
  }
  try {
    return JSON.parse(node.textContent || "{}");
  } catch (_err) {
    return {};
  }
}

const bootstrap = readBootstrap();

function t(path, fallback = "") {
  if (!path) {
    return fallback;
  }
  const normalized = path.startsWith("check_entries.") ? path.slice("check_entries.".length) : path;
  const value = normalized.split(".").reduce((acc, key) => {
    if (acc && typeof acc === "object" && key in acc) {
      return acc[key];
    }
    return undefined;
  }, appCopy);
  return typeof value === "string" ? value : fallback;
}

function formatTemplate(template, values = {}) {
  if (typeof template !== "string") {
    return "";
  }
  return template.replace(/\{(\w+)\}/g, (_, key) => (values[key] !== undefined ? values[key] : ""));
}

function CheckEntriesApp() {
  useEffect(() => {
    const initialJobId = bootstrap.initial_job_id || "";
    const authEmail = bootstrap.user_email || "";
    const ocrLang = OCR_LANG_MAP[String(currentLang).toLowerCase()] || "eng";

    const state = {
      sessionId: null,
      columns: [],
      mapping: {},
      downloadUrls: {},
      results: [],
      decisions: new Map(),
      attachedPdfCount: 0,
    };

    const appRoot = document.getElementById("appRoot");
    const runEmailNotice = document.getElementById("runEmailNotice");
    const runJobNotice = document.getElementById("runJobNotice");
    const journalFileInput = document.getElementById("journalFile");
    const journalSelectedFile = document.getElementById("journalSelectedFile");
    const pdfFilesInput = document.getElementById("pdfFiles");
    const pdfSelectedFiles = document.getElementById("pdfSelectedFiles");
    const runChecksButton = document.getElementById("runChecks");

    const RUN_POLL_DELAY_MS = 5000;
    let activeRunJobId = null;
    let runPollTimer = null;

    function apiRequest(path, options = {}) {
      const headers = new Headers(options.headers || {});
      let body = options.body;
      if (body && !(body instanceof FormData)) {
        if (typeof body !== "string") {
          headers.set("Content-Type", "application/json");
          body = JSON.stringify(body);
        } else if (!headers.has("Content-Type")) {
          headers.set("Content-Type", "application/json");
        }
      }
      const init = { ...options, headers, body };
      let url;
      if (/^https?:\/\//i.test(path)) {
        url = new URL(path);
      } else if (path.startsWith("/check/")) {
        url = new URL(path, window.location.origin);
      } else {
        url = new URL(`${apiBase}${path}`, window.location.origin);
      }
      if (!url.searchParams.has("lang")) {
        url.searchParams.set("lang", currentLang);
      }
      return fetch(url, init).then(async (resp) => {
        if (!resp.ok) {
          let detail = resp.statusText;
          try {
            const payload = await resp.json();
            detail = payload.detail || detail;
          } catch (_err) {
            // ignore parse issues
          }
          throw new Error(detail);
        }
        const type = resp.headers.get("Content-Type") || "";
        if (type.includes("application/json")) {
          return resp.json();
        }
        return resp.blob();
      });
    }

    function showStatus(elementId, message, isError = false) {
      const target = document.getElementById(elementId);
      if (!target) {
        return;
      }
      target.textContent = message || "";
      target.classList.toggle("status-bar__error", !!isError);
    }

    function setRunButtonBusy(isBusy) {
      if (!runChecksButton) {
        return;
      }
      runChecksButton.disabled = !!isBusy;
    }

    function updateEmailNotice() {
      if (!runEmailNotice) {
        return;
      }
      const label = authEmail || t("check_entries.messages.run_checks_email_label", "your sign-in address");
      const template = t(
        "check_entries.messages.run_checks_email_notice",
        "We'll email {email} when the checks finish. Feel free to close this page.",
      );
      runEmailNotice.textContent = template.replace("{email}", label);
    }

    function updateJobNotice(jobId) {
      if (!runJobNotice) {
        return;
      }
      if (!jobId) {
        runJobNotice.textContent = "";
        runJobNotice.hidden = true;
        return;
      }
      const template = t(
        "check_entries.messages.run_checks_job_id",
        "Job ID: {jobId}. Save this ID in case email delivery is delayed.",
      );
      runJobNotice.textContent = formatTemplate(template, { jobId });
      runJobNotice.hidden = false;
    }

    function abortRunJob() {
      if (runPollTimer) {
        clearTimeout(runPollTimer);
        runPollTimer = null;
      }
      activeRunJobId = null;
    }

    function startRunJob(payload) {
      return apiRequest(`/session/${state.sessionId}/run/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }

    function fetchRunJob(jobId) {
      if (state.sessionId) {
        return apiRequest(`/session/${state.sessionId}/run/jobs/${jobId}`, { method: "GET" });
      }
      return apiRequest(`/run/jobs/${jobId}`, { method: "GET" });
    }

    function handleRunJobFailure(message) {
      abortRunJob();
      setRunButtonBusy(false);
      showStatus(
        "runStatus",
        message || t("check_entries.messages.run_checks_failed", "Automatic check failed. Please try again."),
        true,
      );
    }

    function pollRunJob(jobId, attempt) {
      fetchRunJob(jobId)
        .then((data) => {
          if (jobId !== activeRunJobId) {
            return;
          }
          if (data.session_id && !state.sessionId) {
            state.sessionId = data.session_id;
          }
          const status = data.status || "pending";
          if (status === "pending" || status === "running") {
            showStatus("runStatus", t("check_entries.messages.run_checks_init", "Running checks..."));
            runPollTimer = setTimeout(() => pollRunJob(jobId, attempt + 1), RUN_POLL_DELAY_MS);
            return;
          }

          abortRunJob();
          setRunButtonBusy(false);

          if (status === "completed" && data.result) {
            renderRunResults(data.result);
            return;
          }

          handleRunJobFailure(data.error);
        })
        .catch((err) => {
          if (jobId !== activeRunJobId) {
            return;
          }
          handleRunJobFailure(err.message);
        });
    }

    function renderPreview(preview) {
      const container = document.getElementById("journalPreviewContainer");
      const table = document.getElementById("journalPreview");
      if (!container || !table) {
        return;
      }
      container.hidden = !preview;
      if (!preview) {
        return;
      }
      table.innerHTML = "";
      const thead = document.createElement("thead");
      const headerRow = document.createElement("tr");
      preview.columns.forEach((col) => {
        const th = document.createElement("th");
        th.textContent = col;
        headerRow.appendChild(th);
      });
      thead.appendChild(headerRow);
      table.appendChild(thead);
      const tbody = document.createElement("tbody");
      preview.rows.forEach((row) => {
        const tr = document.createElement("tr");
        row.forEach((cell) => {
          const td = document.createElement("td");
          td.textContent = cell === null || cell === undefined ? "" : cell;
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
    }

    function populateMappingSelects() {
      const selects = document.querySelectorAll("#mappingForm select");
      selects.forEach((select) => {
        select.innerHTML = "";
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "-";
        select.appendChild(placeholder);
        state.columns.forEach((col) => {
          const opt = document.createElement("option");
          opt.value = col;
          opt.textContent = col;
          select.appendChild(opt);
        });
      });
    }

    function applyMappingToForm() {
      const selects = document.querySelectorAll("#mappingForm select");
      selects.forEach((select) => {
        const key = select.dataset.key;
        if (!key) {
          return;
        }
        const value = state.mapping[key] || "";
        select.value = value;
      });
    }

    function refreshJournalLabel() {
      if (!journalSelectedFile || !journalFileInput) {
        return;
      }
      journalSelectedFile.textContent =
        journalFileInput.files && journalFileInput.files[0]
          ? journalFileInput.files[0].name
          : t("check_entries.labels.no_file", t("labels.no_file", "No file selected"));
    }

    function refreshPdfLabel() {
      if (!pdfFilesInput || !pdfSelectedFiles) {
        return;
      }
      if (!pdfFilesInput.files || !pdfFilesInput.files.length) {
        if (state.attachedPdfCount > 0) {
          pdfSelectedFiles.textContent = formatTemplate(
            t("check_entries.messages.pdfs_attached", "Attached {count} PDF(s)."),
            { count: state.attachedPdfCount },
          );
        } else {
          pdfSelectedFiles.textContent = t(
            "check_entries.labels.no_files",
            t("labels.no_files", "No files selected"),
          );
        }
        return;
      }
      if (pdfFilesInput.files.length === 1) {
        pdfSelectedFiles.textContent = pdfFilesInput.files[0].name;
        return;
      }
      pdfSelectedFiles.textContent = formatTemplate(
        t("check_entries.labels.files_selected", "{count} files selected"),
        { count: pdfFilesInput.files.length },
      );
    }

    function uploadPdfFiles() {
      if (!pdfFilesInput || !pdfFilesInput.files.length) {
        return;
      }
      if (!state.sessionId) {
        showStatus("pdfStatus", t("check_entries.messages.upload_first", "Upload the journal first."), true);
        return;
      }
      const formData = new FormData();
      Array.from(pdfFilesInput.files).forEach((file) => formData.append("files", file));
      showStatus("pdfStatus", t("check_entries.messages.uploading_pdfs", "Uploading PDFs..."));
      apiRequest(`/session/${state.sessionId}/pdfs`, { method: "POST", body: formData })
        .then((data) => {
          state.attachedPdfCount = typeof data.count === "number" ? data.count : state.attachedPdfCount;
          const statusMessage = formatTemplate(
            t("check_entries.messages.pdfs_attached", "Attached {count} PDF(s)."),
            { count: state.attachedPdfCount },
          );
          showStatus("pdfStatus", "");
          if (pdfSelectedFiles) {
            pdfSelectedFiles.textContent = statusMessage;
          }
        })
        .catch((err) => showStatus("pdfStatus", err.message, true))
        .finally(() => {
          if (pdfFilesInput) {
            pdfFilesInput.value = "";
          }
          refreshPdfLabel();
        });
    }

    function uploadJournalFile() {
      if (!journalFileInput || !journalFileInput.files.length) {
        return;
      }
      const formData = new FormData();
      formData.append("file", journalFileInput.files[0]);
      showStatus("uploadStatus", t("check_entries.messages.uploading", "Uploading..."));
      apiRequest("/upload", { method: "POST", body: formData })
        .then((data) => {
          state.sessionId = data.session_id;
          state.columns = data.columns || [];
          state.mapping = {};
          state.attachedPdfCount = 0;
          state.decisions.clear();
          state.results = [];
          state.downloadUrls = {};

          const resultsPanel = document.getElementById("resultsPanel");
          const reviewSection = document.getElementById("reviewSection");
          const mappingPanel = document.getElementById("mappingPanel");
          const pdfPanel = document.getElementById("pdfPanel");
          const parametersPanel = document.getElementById("parametersPanel");

          if (resultsPanel) {
            resultsPanel.hidden = true;
          }
          if (reviewSection) {
            reviewSection.hidden = true;
          }
          if (mappingPanel) {
            mappingPanel.hidden = false;
          }
          if (pdfPanel) {
            pdfPanel.hidden = false;
          }
          if (parametersPanel) {
            parametersPanel.hidden = false;
          }

          updateJobNotice(null);
          renderPreview(data.preview);
          populateMappingSelects();
          applyMappingToForm();
          showStatus("mappingStatus", "");
          showStatus(
            "uploadStatus",
            formatTemplate(
              t("check_entries.messages.upload_status", "Loaded {rows} rows from {filename}."),
              { rows: data.row_count.toLocaleString(), filename: data.filename },
            ),
          );
          refreshPdfLabel();
          if (pdfFilesInput && pdfFilesInput.files.length) {
            uploadPdfFiles();
          }
        })
        .catch((err) => {
          const detail = (err && err.message) || t("check_entries.messages.upload_failed", "Upload failed.");
          showStatus("uploadStatus", detail, true);
        })
        .finally(() => {
          if (journalFileInput) {
            journalFileInput.value = "";
          }
        });
    }

    function renderSummary(text, tables) {
      const summaryNode = document.getElementById("summaryText");
      const tablesNode = document.getElementById("summaryTables");
      if (summaryNode) {
        summaryNode.textContent = text || "";
      }
      if (!tablesNode) {
        return;
      }
      tablesNode.innerHTML = "";
      (tables || []).forEach((tbl) => {
        const section = document.createElement("section");
        section.className = "summary-table";
        const title = document.createElement("h4");
        title.textContent = tbl.name;
        section.appendChild(title);
        const table = document.createElement("table");
        const thead = document.createElement("thead");
        const headerRow = document.createElement("tr");
        tbl.columns.forEach((col) => {
          const th = document.createElement("th");
          th.textContent = col;
          headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);
        const tbody = document.createElement("tbody");
        tbl.rows.forEach((row) => {
          const tr = document.createElement("tr");
          row.forEach((cell) => {
            const td = document.createElement("td");
            td.textContent = cell === null || cell === undefined ? "" : cell;
            tr.appendChild(td);
          });
          tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        section.appendChild(table);
        tablesNode.appendChild(section);
      });

      const downloadExcel = document.getElementById("downloadExcel");
      const downloadSummary = document.getElementById("downloadSummary");
      if (downloadExcel) {
        downloadExcel.onclick = () => openDownload("excel", "check_results.xlsx");
      }
      if (downloadSummary) {
        downloadSummary.onclick = () => openDownload("summary", "check_summary.txt");
      }
    }

    function renderResultsTable(rows) {
      const tableSection = document.getElementById("resultsTable");
      const table = document.getElementById("resultsData");
      if (!tableSection || !table) {
        return;
      }
      table.innerHTML = "";
      if (!rows || !rows.length) {
        tableSection.hidden = true;
        return;
      }
      tableSection.hidden = false;
      const columns = Object.keys(rows[0]);
      const thead = document.createElement("thead");
      const headerRow = document.createElement("tr");
      columns.forEach((col) => {
        const th = document.createElement("th");
        th.textContent = col;
        headerRow.appendChild(th);
      });
      thead.appendChild(headerRow);
      table.appendChild(thead);
      const tbody = document.createElement("tbody");
      rows.forEach((row) => {
        const tr = document.createElement("tr");
        columns.forEach((col) => {
          const td = document.createElement("td");
          const value = row[col];
          if (col === "mismatches" && Array.isArray(value)) {
            td.textContent = value.length ? `${value.length} mismatch(es)` : "";
          } else if (typeof value === "object" && value !== null) {
            td.textContent = JSON.stringify(value);
          } else {
            td.textContent = value === null || value === undefined ? "" : value;
          }
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
    }

    function openPdf(movement) {
      const base = state.downloadUrls.pdf;
      if (!base) {
        return;
      }
      const separator = base.includes("?") ? "&" : "?";
      const path = `${base}${separator}movement=${encodeURIComponent(movement)}`;
      apiRequest(path, { method: "GET" })
        .then((blob) => {
          const url = URL.createObjectURL(blob);
          window.open(url, "_blank");
          setTimeout(() => URL.revokeObjectURL(url), 5000);
        })
        .catch((err) =>
          showStatus(
            "reviewStatus",
            err.message || t("check_entries.messages.pdf_download_failed", "PDF download failed"),
            true,
          ),
        );
    }

    function openDownload(kind, filename) {
      const path = state.downloadUrls[kind];
      if (!path) {
        return;
      }
      apiRequest(path, { method: "GET" })
        .then((blob) => {
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = filename;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          URL.revokeObjectURL(url);
        })
        .catch((err) =>
          showStatus("runStatus", err.message || t("check_entries.messages.download_failed", "Download failed"), true),
        );
    }

    function renderMismatches(rows) {
      const list = document.getElementById("mismatchList");
      const section = document.getElementById("reviewSection");
      if (!list || !section) {
        return;
      }
      list.innerHTML = "";
      const mismatches = rows.filter((row) => (row.check_status || "") === "mismatch");
      section.hidden = mismatches.length === 0;
      if (!mismatches.length) {
        return;
      }

      mismatches.forEach((row) => {
        const card = document.createElement("article");
        card.className = "mismatch-card";

        const title = document.createElement("h4");
        title.textContent = formatTemplate(t("check_entries.labels.movement_title", "Movement {movement}"), {
          movement: row.movement_number || "",
        });
        card.appendChild(title);

        const explanationList = document.createElement("div");
        explanationList.className = "mismatch-explanations";
        (row.mismatches || []).forEach((item) => {
          const block = document.createElement("div");
          block.className = "mismatch-explanation";
          const label = document.createElement("strong");
          label.textContent = item.mismatch_type || "Mismatch";
          block.appendChild(label);
          const text = document.createElement("p");
          text.textContent = item.explanation || "";
          block.appendChild(text);
          explanationList.appendChild(block);
        });
        card.appendChild(explanationList);

        const actions = document.createElement("div");
        actions.className = "mismatch-actions";

        const select = document.createElement("select");
        select.innerHTML = `
          <option value="mismatch">${t("check_entries.labels.mismatch_option", "Mismatch")}</option>
          <option value="ok">${t("check_entries.labels.ok_option", "OK")}</option>
        `;
        select.value = state.decisions.get(row.movement_number) || "mismatch";
        select.addEventListener("change", () => {
          state.decisions.set(row.movement_number, select.value);
        });
        actions.appendChild(select);

        const textarea = document.createElement("textarea");
        textarea.placeholder = t(
          "check_entries.labels.override_placeholder",
          "Reason for override (optional)",
        );
        textarea.addEventListener("input", () => {
          const decision = state.decisions.get(row.movement_number) || "mismatch";
          state.decisions.set(row.movement_number, decision);
          state.decisions.set(`${row.movement_number}_reason`, textarea.value);
        });
        textarea.value = state.decisions.get(`${row.movement_number}_reason`) || "";
        actions.appendChild(textarea);

        const pdfButton = document.createElement("button");
        pdfButton.type = "button";
        pdfButton.className = "ghost-button";
        pdfButton.textContent = t("check_entries.labels.download_pdf", "Download PDF");
        pdfButton.addEventListener("click", () => openPdf(row.movement_number));
        actions.appendChild(pdfButton);

        card.appendChild(actions);
        list.appendChild(card);
      });
    }

    function renderRunResults(data) {
      const usedBatch = !!data.batch_mode;
      const statusKey = usedBatch
        ? "check_entries.messages.run_checks_batch_pending"
        : "check_entries.messages.run_checks_done";
      const fallbackMsg = usedBatch
        ? "Submitted the automatic check as a batch run. This can take several hours; we'll email you when it finishes."
        : "Checks completed.";
      showStatus("runStatus", t(statusKey, fallbackMsg));

      state.downloadUrls = data.download_urls || {};
      state.results = data.results || [];
      state.decisions.clear();
      state.results.forEach((row) => {
        const movement = row.movement_number || "";
        if (!movement) {
          return;
        }
        if (row.review_status) {
          state.decisions.set(movement, row.review_status);
        }
        if (row.review_reason) {
          state.decisions.set(`${movement}_reason`, row.review_reason);
        }
      });

      const resultsPanel = document.getElementById("resultsPanel");
      if (resultsPanel) {
        resultsPanel.hidden = false;
      }
      renderSummary(data.summary_text, data.summary_tables);
      renderResultsTable(state.results);
      renderMismatches(state.results);
    }

    function onAutoMap() {
      if (!state.sessionId) {
        showStatus("mappingStatus", t("check_entries.messages.upload_first", "Upload the journal first."), true);
        return;
      }
      apiRequest(`/session/${state.sessionId}/mapping/auto`, { method: "POST" })
        .then((data) => {
          state.mapping = data.mapping || {};
          applyMappingToForm();
          showStatus(
            "mappingStatus",
            t("check_entries.messages.auto_mapping_ok", "Column mapping suggested automatically."),
          );
        })
        .catch((err) => showStatus("mappingStatus", err.message, true));
    }

    function onSaveMapping() {
      if (!state.sessionId) {
        showStatus("mappingStatus", t("check_entries.messages.upload_first", "Upload the journal first."), true);
        return;
      }
      const mapping = {};
      const selects = document.querySelectorAll("#mappingForm select");
      selects.forEach((select) => {
        const key = select.dataset.key;
        if (!key) {
          return;
        }
        mapping[key] = select.value || null;
      });
      apiRequest(`/session/${state.sessionId}/mapping`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mapping }),
      })
        .then((data) => {
          state.mapping = data.mapping ?? mapping;
          showStatus("mappingStatus", t("check_entries.messages.mapping_saved", "Mapping saved."));
        })
        .catch((err) => showStatus("mappingStatus", err.message, true));
    }

    function onRunChecks() {
      if (!state.sessionId) {
        showStatus("runStatus", t("check_entries.messages.upload_first", "Upload the journal first."), true);
        return;
      }
      if (!state.attachedPdfCount || state.attachedPdfCount <= 0) {
        showStatus(
          "runStatus",
          t("check_entries.messages.run_checks_pdfs", "Upload supporting PDF files before running."),
          true,
        );
        abortRunJob();
        setRunButtonBusy(false);
        return;
      }
      if (!state.mapping || Object.keys(state.mapping).length === 0) {
        showStatus(
          "runStatus",
          t("check_entries.messages.run_checks_mapping", "Save the column mapping before running."),
          true,
        );
        abortRunJob();
        setRunButtonBusy(false);
        return;
      }

      const paramDebug = document.getElementById("paramDebug");
      const paramAmount = document.getElementById("paramAmount");
      const paramDateWindow = document.getElementById("paramDateWindow");
      const paramTiming = document.getElementById("paramTiming");
      const paramBeneficiaryMode = document.getElementById("paramBeneficiaryMode");
      const paramSimilarity = document.getElementById("paramSimilarity");

      const payload = {
        lang: ocrLang,
        debug: !!(paramDebug && paramDebug.checked),
        amount_tolerance: parseFloat((paramAmount && paramAmount.value) || "0"),
        date_window: parseInt((paramDateWindow && paramDateWindow.value) || "0", 10),
        timing_difference_window: parseInt((paramTiming && paramTiming.value) || "0", 10),
        beneficiary_check_mode: (paramBeneficiaryMode && paramBeneficiaryMode.value) || "compare",
        beneficiary_similarity: parseFloat((paramSimilarity && paramSimilarity.value) || "0"),
        notify_email: authEmail || null,
      };

      abortRunJob();
      setRunButtonBusy(true);
      showStatus("runStatus", t("check_entries.messages.run_checks_init", "Running checks..."));

      startRunJob(payload)
        .then((data) => {
          if (!data || !data.job_id) {
            throw new Error(t("check_entries.messages.run_checks_failed", "Automatic check failed. Please try again."));
          }
          activeRunJobId = data.job_id;
          updateEmailNotice();
          updateJobNotice(activeRunJobId);
          showStatus("runStatus", t("check_entries.messages.run_checks_init", "Running checks..."));
          pollRunJob(activeRunJobId, 0);
        })
        .catch((err) => {
          handleRunJobFailure(err.message);
        });
    }

    function onApplyReview() {
      if (!state.sessionId) {
        showStatus("reviewStatus", t("check_entries.messages.review_first", "Run the checks first."), true);
        return;
      }
      const decisions = [];
      state.results
        .filter((row) => (row.check_status || "") === "mismatch")
        .forEach((row) => {
          const movement = row.movement_number || "";
          const status = state.decisions.get(movement) || "mismatch";
          const reason = state.decisions.get(`${movement}_reason`) || "";
          decisions.push({ movement, status, reason });
        });

      apiRequest(`/session/${state.sessionId}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decisions }),
      })
        .then(renderRunResults)
        .catch((err) => showStatus("reviewStatus", err.message, true));
    }

    const uploadCards = Array.from(document.querySelectorAll(".upload-card"));
    const uploadCardHandlers = uploadCards
      .map((card) => {
        const inputId = card.dataset.targetInput;
        const inputEl = inputId ? document.getElementById(inputId) : null;
        if (!inputEl) {
          return null;
        }
        const handler = () => inputEl.click();
        card.addEventListener("click", handler);
        return { card, handler };
      })
      .filter(Boolean);

    const onJournalChange = () => {
      refreshJournalLabel();
      if (journalFileInput && journalFileInput.files.length) {
        uploadJournalFile();
      }
    };

    const onPdfChange = () => {
      refreshPdfLabel();
      if (pdfFilesInput && pdfFilesInput.files.length) {
        uploadPdfFiles();
      }
    };

    const autoMapButton = document.getElementById("autoMap");
    const saveMappingButton = document.getElementById("saveMapping");
    const runChecksBtn = document.getElementById("runChecks");
    const applyReviewButton = document.getElementById("applyReview");

    if (journalFileInput) {
      journalFileInput.addEventListener("change", onJournalChange);
    }
    if (pdfFilesInput) {
      pdfFilesInput.addEventListener("change", onPdfChange);
    }
    if (autoMapButton) {
      autoMapButton.addEventListener("click", onAutoMap);
    }
    if (saveMappingButton) {
      saveMappingButton.addEventListener("click", onSaveMapping);
    }
    if (runChecksBtn) {
      runChecksBtn.addEventListener("click", onRunChecks);
    }
    if (applyReviewButton) {
      applyReviewButton.addEventListener("click", onApplyReview);
    }

    if (appRoot) {
      appRoot.hidden = false;
    }
    refreshJournalLabel();
    refreshPdfLabel();

    if (initialJobId) {
      activeRunJobId = initialJobId;
      setRunButtonBusy(true);
      updateEmailNotice();
      updateJobNotice(activeRunJobId);
      showStatus("runStatus", t("check_entries.messages.run_checks_init", "Running checks..."));
      pollRunJob(activeRunJobId, 0);
    }

    return () => {
      abortRunJob();
      if (journalFileInput) {
        journalFileInput.removeEventListener("change", onJournalChange);
      }
      if (pdfFilesInput) {
        pdfFilesInput.removeEventListener("change", onPdfChange);
      }
      if (autoMapButton) {
        autoMapButton.removeEventListener("click", onAutoMap);
      }
      if (saveMappingButton) {
        saveMappingButton.removeEventListener("click", onSaveMapping);
      }
      if (runChecksBtn) {
        runChecksBtn.removeEventListener("click", onRunChecks);
      }
      if (applyReviewButton) {
        applyReviewButton.removeEventListener("click", onApplyReview);
      }
      uploadCardHandlers.forEach((entry) => {
        if (!entry || !entry.card || !entry.handler) {
          return;
        }
        entry.card.removeEventListener("click", entry.handler);
      });
    };
  }, []);

  return (
    <>
      <header className="landing-header">
        <a href={`/?lang=${currentLang || "en"}`} className="landing-logo-link" aria-label="Return to the home page">
          <img className="landing-logo" src="https://mparanza.com/images/MPARANZA-HORIZONTAL.png" alt="Mparanza" />
        </a>
      </header>

      <h1
        className="page-title page-title--with-help"
        data-tooltip={t(
          "page_help",
          "Upload the journal, map columns, attach PDFs, run the checks, and download the flagged entries.",
        )}
        aria-label={t(
          "page_help",
          "Upload the journal, map columns, attach PDFs, run the checks, and download the flagged entries.",
        )}
      >
        {bootstrap.page_label || "Check entries"}
      </h1>

      <main id="appRoot" className="app-main">
        <div className="container">
          <section className="panel" id="uploadPanel">
            <div className="panel-header">
              <h2
                className="panel-title panel-title--with-help"
                data-tooltip={t("panels.upload.subtitle", "Upload the ledger extract to analyse.")}
                aria-label={t("panels.upload.subtitle", "Upload the ledger extract to analyse.")}
              >
                {t("panels.upload.title", "Upload sample file")}
              </h2>
            </div>
            <div className="field file-field compact-upload">
              <input type="file" id="journalFile" accept=".xlsx,.xls,.csv,.pdf" hidden />
              <div className="upload-card" data-target-input="journalFile">
                <span className="upload-icon" aria-hidden="true">
                  <img src="/static/icons/upload.svg" alt="" />
                </span>
                <span className="upload-label">{t("labels.select_journal", "Select journal file")}</span>
              </div>
              <p className="selected-file" id="journalSelectedFile">
                {t("labels.no_file", "No file selected")}
              </p>
            </div>
            <div id="uploadStatus" className="status-bar"></div>
            <div className="table-scroll" id="journalPreviewContainer" hidden>
              <table id="journalPreview"></table>
            </div>
          </section>

          <section className="panel" id="mappingPanel" hidden>
            <div className="panel-header">
              <h2
                className="panel-title panel-title--with-help"
                data-tooltip={t(
                  "panels.mapping.subtitle",
                  "Confirm which columns correspond to the required fields.",
                )}
                aria-label={t(
                  "panels.mapping.subtitle",
                  "Confirm which columns correspond to the required fields.",
                )}
              >
                {t("panels.mapping.title", "Column mapping")}
              </h2>
            </div>
            <div className="actions">
              <button id="autoMap" className="ghost-button" type="button">
                {t("buttons.auto_map", "Auto-map columns")}
              </button>
            </div>
            <form id="mappingForm" className="mapping-grid">
              <label>
                {t("labels.mapping_fields.movement_number", "Movement number")}
                <select data-key="movement_number"></select>
              </label>
              <label>
                {t("labels.mapping_fields.amount", "Amount")}
                <select data-key="amount"></select>
              </label>
              <label>
                {t("labels.mapping_fields.debit_amount", "Debit amount")}
                <select data-key="debit_amount"></select>
              </label>
              <label>
                {t("labels.mapping_fields.credit_amount", "Credit amount")}
                <select data-key="credit_amount"></select>
              </label>
              <label>
                {t("labels.mapping_fields.date", "Date")}
                <select data-key="date"></select>
              </label>
              <label>
                {t("labels.mapping_fields.account", "Account")}
                <select data-key="account"></select>
              </label>
              <label>
                {t("labels.mapping_fields.account_desc", "Account description")}
                <select data-key="account_desc"></select>
              </label>
              <label>
                {t("labels.mapping_fields.line_desc", "Line description")}
                <select data-key="line_desc"></select>
              </label>
              <label>
                {t("labels.mapping_fields.beneficiary", "Beneficiary")}
                <select data-key="beneficiary"></select>
              </label>
            </form>
            <div className="actions">
              <button id="saveMapping" className="primary-button" type="button">
                {t("buttons.save_mapping", "Save mapping")}
              </button>
            </div>
            <div id="mappingStatus" className="status-bar"></div>
          </section>

          <section className="panel" id="pdfPanel" hidden>
            <div className="panel-header">
              <h2
                className="panel-title panel-title--with-help"
                data-tooltip={t("panels.pdf.subtitle", "Attach the supporting documents to match against.")}
                aria-label={t("panels.pdf.subtitle", "Attach the supporting documents to match against.")}
              >
                {t("panels.pdf.title", "Upload PDFs")}
              </h2>
            </div>
            <div className="field file-field compact-upload">
              <input type="file" id="pdfFiles" accept="application/pdf" multiple hidden />
              <div className="upload-card" data-target-input="pdfFiles">
                <span className="upload-icon" aria-hidden="true">
                  <img src="/static/icons/upload.svg" alt="" />
                </span>
                <span className="upload-label">{t("labels.select_pdfs", "Select PDF files")}</span>
              </div>
              <p className="selected-file" id="pdfSelectedFiles">
                {t("labels.no_files", "No files selected")}
              </p>
            </div>
            <div id="pdfStatus" className="status-bar"></div>
          </section>

          <section className="panel" id="parametersPanel" hidden>
            <div className="panel-header">
              <h2
                className="panel-title panel-title--with-help"
                data-tooltip={t(
                  "panels.parameters.subtitle",
                  "Adjust tolerances and beneficiary comparison settings.",
                )}
                aria-label={t(
                  "panels.parameters.subtitle",
                  "Adjust tolerances and beneficiary comparison settings.",
                )}
              >
                {t("panels.parameters.title", "Configure checks")}
              </h2>
            </div>
            <form id="parametersForm" className="parameters-grid">
              <label>
                {t("labels.amount_tolerance", "Amount tolerance")}
                <input type="number" id="paramAmount" min="0" step="0.1" defaultValue="1" />
              </label>
              <label>
                {t("labels.date_window", "Date window (days)")}
                <input type="number" id="paramDateWindow" min="0" max="31" defaultValue="3" />
              </label>
              <label>
                {t("labels.timing_diff", "Timing difference (days)")}
                <input type="number" id="paramTiming" min="0" max="31" defaultValue="5" />
              </label>
              <label>
                {t("labels.beneficiary_check", "Beneficiary check")}
                <select id="paramBeneficiaryMode" defaultValue="compare">
                  <option value="compare">{t("options.beneficiary_modes.compare", "Compare")}</option>
                  <option value="extract_only">{t("options.beneficiary_modes.extract_only", "Extract only")}</option>
                  <option value="off">{t("options.beneficiary_modes.off", "Off")}</option>
                </select>
              </label>
              <label>
                {t("labels.beneficiary_similarity", "Beneficiary similarity (%)")}
                <input type="number" id="paramSimilarity" min="0" max="100" defaultValue="70" />
              </label>
              <label className="toggle">
                <input id="paramDebug" type="checkbox" />
                <span className="toggle__label">
                  {t("labels.include_debug", "Include debug columns in excel")}
                </span>
              </label>
            </form>
            <div className="actions">
              <span
                className="panel-title panel-title--with-help actions__button-help"
                data-tooltip={t(
                  "messages.run_checks_help",
                  "Click to run checks. Checks can last from a few minutes to a few hours.",
                )}
              >
                <button
                  id="runChecks"
                  className="primary-button"
                  type="button"
                  aria-label={t(
                    "messages.run_checks_help",
                    "Click to run checks. Checks can last from a few minutes to a few hours.",
                  )}
                >
                  {t("buttons.run_checks", "Run automatic check")}
                </button>
              </span>
              <span id="runEmailNotice" className="actions__hint" aria-live="polite" aria-atomic="true">
                &nbsp;
              </span>
              <span
                id="runJobNotice"
                className="actions__hint"
                aria-live="polite"
                aria-atomic="true"
                hidden
              ></span>
            </div>
            <div id="runStatus" className="status-bar"></div>
          </section>

          <section className="panel" id="resultsPanel" hidden>
            <div className="panel-header">
              <h2
                className="panel-title panel-title--with-help"
                data-tooltip={t(
                  "panels.results.subtitle",
                  "Review mismatches, download reports, and apply overrides.",
                )}
                aria-label={t(
                  "panels.results.subtitle",
                  "Review mismatches, download reports, and apply overrides.",
                )}
              >
                {t("panels.results.title", "Results")}
              </h2>
            </div>
            <div className="actions">
              <button id="downloadExcel" className="ghost-button" type="button">
                {t("buttons.download_excel", "Download Excel")}
              </button>
              <button id="downloadSummary" className="ghost-button" type="button">
                {t("buttons.download_summary", "Download summary")}
              </button>
            </div>
            <article id="summaryText" className="summary-text"></article>
            <div id="summaryTables" className="summary-grid"></div>
            <section id="reviewSection" hidden>
              <h3>{t("labels.mismatches_title", "Mismatches")}</h3>
              <div id="mismatchList" className="mismatch-grid"></div>
              <div className="actions">
                <button id="applyReview" className="primary-button" type="button">
                  {t("buttons.apply_review", "Apply review")}
                </button>
              </div>
              <div id="reviewStatus" className="status-bar"></div>
            </section>
            <section id="resultsTable" className="table-scroll" hidden>
              <table id="resultsData"></table>
            </section>
          </section>
        </div>
      </main>
    </>
  );
}

const rootNode = document.getElementById("checkEntriesReactApp");
if (rootNode) {
  createRoot(rootNode).render(<CheckEntriesApp />);
}

    const deskText = (key) => (DESK_TEXT[activeLanguage()] || DESK_TEXT.en)[key] || DESK_TEXT.en[key] || key;
    const deskGroup = (item) => /artifact$/.test(item.item_type) ? "documents" : ["check_exception", "source_processing_issue"].includes(item.item_type) ? "exceptions" : "accounting";
    const deskStatus = (item) => item.data?.deterministic_status || item.data?.reconciliation_status || "unknown";
    const deskValue = (data, keys) => keys.map(key => data[key]).find(value => value !== null && value !== undefined && value !== "");
    const deskMoney = (value, currency) => {
      if (value === undefined || value === null || value === "") return deskText("unavailable");
      const number = Number(value);
      if (!Number.isFinite(number)) return String(value);
      return new Intl.NumberFormat(activeLanguage(), {minimumFractionDigits:2, maximumFractionDigits:2}).format(number) + (currency ? ` ${currency}` : "");
    };
    const deskTitle = (item) => {
      if (deskGroup(item) === "accounting") return [item.data?.document_no || item.data?.document_key || item.id, item.data?.counterparty].filter(Boolean).join(" · ");
      if (deskGroup(item) === "documents") return item.output_path || item.title;
      return deskText(item.item_type) + (item.data?.source_file ? ` · ${item.data.source_file}` : "");
    };
    const deskPair = (label, value) => `<dt>${esc(deskText(label))}</dt><dd>${esc(value === undefined || value === null || value === "" ? deskText("unavailable") : formatValue(value))}</dd>`;
    function renderSummary() {
      const summary = reviewPayload().summary || {};
      const assumptions = state.payload.run_intake?.assumptions || {};
      const accounting = items().filter(item => deskGroup(item) === "accounting");
      const counts = summary.reconciliation_status_counts || {};
      document.getElementById("subtitle").textContent = deskText("purpose");
      document.getElementById("summary").innerHTML = `<div class="desk-facts"><span>${esc(deskText("population"))}: <strong>${esc(summary.reconciliation_row_count ?? deskText("unavailable"))}</strong></span><span>${esc(deskText("cutoff"))}: <strong>${esc(assumptions.cutoff_date || deskText("unavailable"))}</strong></span><span>${esc(deskText("reviewScope"))}: <strong>${accounting.length}</strong></span></div><div class="desk-results">${Object.entries(counts).map(([key,value]) => `<span><strong>${esc(value)}</strong> ${esc(deskText(key))}</span>`).join("")}</div><p class="desk-note">${esc(deskText("scopeNote"))}</p>`;
    }
    function renderProgress() {
      const total = items().length;
      document.getElementById("decision-progress").textContent = `${deskText("reviewProgress")}: ${validDecisionCount()} / ${total}`;
      document.getElementById("decision-progress-fill").style.width = `${total ? validDecisionCount()/total*100 : 0}%`;
      document.getElementById("decision-pill").textContent = "";
      document.getElementById("use-recommended").disabled = true;
      document.getElementById("save-decisions").disabled = !validDecisionCount();
      document.getElementById("apply-decisions").disabled = !validDecisionCount();
      renderReviewStore();
      renderRecoveryPanel();
    }
    function renderReviewStore() {
      const saved = savedDecisionInputs();
      const current = collectDecisionInputs();
      const changed = changedDecisionCount(current, saved);
      const applied = appliedDecisionInputs();
      document.getElementById("review-store").textContent = `${deskText("saved")}: ${saved.length} · ${deskText("applied")}: ${applied.length} · ${changed ? deskText("unsaved") : deskText("noUnsaved")}`;
    }
    function filteredItems() {
      const q = state.query.trim().toLowerCase();
      const group = state.selectedType === "all" ? "accounting" : state.selectedType;
      return items().filter(item => deskGroup(item) === group && (state.selectedState === "all" || reviewStateFor(item) === state.selectedState) && (!q || JSON.stringify(item).toLowerCase().includes(q)));
    }
    function renderTabs() {
      const group = state.selectedType === "all" ? "accounting" : state.selectedType;
      document.getElementById("tabs").innerHTML = ["accounting", "exceptions", "documents"].map(key => `<button class="tab" data-type="${key}" aria-pressed="${key === group}">${esc(deskText(key))} (${items().filter(item => deskGroup(item) === key).length})</button>`).join("");
      document.getElementById("desk-section-help").textContent = deskText(`${group}Help`);
      document.getElementById("queue-title").textContent = deskText(group);
    }
    function renderStateStrip() {
      const failed = reviewPayload().summary?.failed_check_count;
      const stage = artifactState();
      const ready = stage === "final_ready";
      document.getElementById("state-strip").innerHTML = `<p class="desk-note"><strong>${esc(deskText("processing"))}:</strong> ${esc(failed > 0 ? `${failed} ${deskText("failedChecks")}` : failed === 0 ? deskText("processed") : deskText("unavailable"))} · <strong>${esc(deskText("deliverables"))}:</strong> ${esc(ready ? deskText("finalReady") : deskText("notFinal"))}</p>`;
    }
    function rowHtml(item) {
      const data = item.data || {};
      const group = deskGroup(item);
      const status = group === "accounting" ? deskText(deskStatus(item)) : deskText(group === "documents" ? "documentReview" : "exceptionReview");
      const decision = decisionFor(item.id);
      return `<button type="button" class="row${item.id === state.selectedId ? " is-selected" : ""}" data-id="${esc(item.id)}" aria-pressed="${item.id === state.selectedId}"><span class="title">${esc(deskTitle(item))}</span><span class="desk-row-meta"><span>${esc(status)}</span><span>${group === "accounting" ? esc(deskMoney(deskValue(data,["amount","balance","open_amount"]),data.currency)) : ""}</span></span><span class="desk-row-meta">${esc(decision ? actionLabel(decision.action) : deskText("toReview"))}</span></button>`;
    }
    function renderRows() {
      const rows = filteredItems();
      if (!rows.some(item => item.id === state.selectedId)) state.selectedId = rows[0]?.id || null;
      document.getElementById("count").textContent = String(rows.length);
      document.getElementById("rows").innerHTML = rows.length ? rows.map(rowHtml).join("") : `<p class="empty">${esc(deskText("noItems"))}</p>`;
      renderDetails(); renderSummary(); renderProgress(); renderStateStrip();
    }
    function actionLabel(action) {
      return deskText(action || "choose");
    }
    function decisionImpactHtml(item, action) {
      const group = deskGroup(item);
      const key = group === "accounting" ? (action || "choose") + "Effect" : group + "Effect";
      return `<p class="decision-impact">${esc(deskText(key))}</p>`;
    }
    function decisionControlsHtml(item) {
      const decision = decisionFor(item.id) || {};
      const action = decision.action || "";
      const field = action === "edit" ? "edit_value" : "reviewer_note";
      const label = action === "edit" ? deskText("newReviewNote") : ui("fields","reviewerNote","Reviewer note");
      return `<section class="decision-box"><div class="decision-grid">${(item.allowed_actions || []).map(candidate => `<button class="decision-choice" type="button" data-decision-action="${esc(candidate)}" aria-pressed="${candidate === action}">${esc(actionLabel(candidate))}</button>`).join("")}</div>${decisionImpactHtml(item,action)}<label class="field"><span class="field-label">${esc(label)}</span><textarea ${action ? "" : "disabled"} data-decision-field="${field}">${esc(decision[field] || "")}</textarea></label>${action === "request_more_documents" ? `<label class="field"><span class="field-label">${esc(ui("fields","requestedDocuments","Requested documents"))}</span><textarea data-decision-field="requested_documents">${esc((decision.requested_documents || []).join("\n"))}</textarea></label>` : ""}</section>`;
    }
    function detailsHtml(item) {
      if (!item) return `<p class="empty">${esc(deskText("noItems"))}</p>`;
      const data = item.data || {};
      const group = deskGroup(item);
      const result = deskStatus(item);
      const amount = deskValue(data,["amount","balance","open_amount"]);
      const supported = ["closed","partially_paid"].includes(result) && data.relationship_control_status !== "failed";
      const settled = supported ? (result === "closed" ? amount : data.allocated_amount) : undefined;
      const residual = supported ? (result === "closed" ? "0" : data.residual_amount) : undefined;
      const source = [data.source_file, data.source_page, data.source_row].filter(value => value !== undefined && value !== null && value !== "").join(" · ") || item.source_path;
      const reference = data.matched_evidence_reference || data.supporting_bank_reference;
      const missing = data.relationship_control_detail === "allocation party mismatch" ? deskText("partyMismatch") : result === "unresolved" ? deskText("noSettlementEvidence") : data.missing_evidence;
      const technical = `<details class="desk-raw"><summary>${esc(deskText("sourceRecord"))}</summary><pre>${esc(JSON.stringify({data:item.data,evidence:item.evidence},null,2))}</pre></details>`;
      let body = `<h3>${esc(deskTitle(item))}</h3>`;
      if (group === "accounting") {
        body += `<p>${esc(deskText(result))}</p><div class="desk-balance">${[["original",amount],["settlement",settled],["residual",residual]].map(([label,value]) => `<div><span>${esc(deskText(label))}</span><strong>${esc(deskMoney(value,data.currency))}</strong></div>`).join("")}</div><p class="desk-note">${esc(deskText(supported ? result === "closed" ? "closedNote" : "partialNote" : "unsupportedNote"))}</p><section class="desk-evidence"><h4>${esc(deskText("evidence"))}</h4><dl>${deskPair("source",source)}${deskPair("reference",reference)}${deskPair("paymentDate",data.supporting_bank_date)}${deskPair("documentDate",data.document_date)}${deskPair("account",data.account)}</dl><p>${esc(deskText(result === "closed" ? "verifyClosed" : result === "partially_paid" ? "verifyPartial" : "verifyOpen"))}</p></section>`;
      } else {
        body += `<p>${esc(deskText(group + "Effect"))}</p><dl>${deskPair("source",source || item.output_path)}${deskPair("finding", data.reason || data.error || data.note)}</dl>`;
      }
      if (missing && result !== "closed") body += `<section class="desk-evidence"><h4>${esc(deskText("missingSupport"))}</h4><p>${esc(result === "partially_paid" ? deskText("partialNote") : missing)}</p></section>`;
      return body + decisionControlsHtml(item) + technical;
    }
    function renderChrome() {
      document.documentElement.lang = activeLanguage();
      document.title = workflowText("title", CONFIG.title);
      document.getElementById("app-title").textContent = document.title;
      document.getElementById("status-pill").textContent = "";
      document.getElementById("diagnostics-title").textContent = deskText("diagnostics");
      document.getElementById("desk-save-help").textContent = deskText("saveHelp");
      document.getElementById("detail-title").textContent = deskText("detailTitle");
      setButtonText("save-decisions",deskText("save"));
      setButtonText("apply-decisions",deskText("apply"));
      setButtonText("copy-decisions",ui("buttons","copyJson","Copy JSON"));
      setButtonText("download-decisions",ui("buttons","downloadJson","Download JSON"));
      document.getElementById("search").placeholder = deskText("search");
      document.getElementById("checkpoint-title").textContent = deskText("checkpointTitle");
      document.getElementById("checkpoint-label").textContent = deskText("checkpointPrompt");
    }
    function applyToolArgs() {
      const checkpoint = document.getElementById("review-checkpoint").value.trim();
      if (!/^[0-9a-f]{64}$/.test(checkpoint)) {
        document.getElementById("checkpoint-details").open = true;
        document.getElementById("review-checkpoint").focus();
        throw new Error(deskText("checkpointRequired"));
      }
      return {run_intake:state.payload.run_intake || null,review_payload:reviewPayload(),ui_decisions:state.payload.ui_decisions || null,final_artifacts:state.payload.final_artifacts || null,decisions:collectDecisionInputs(),decision_source:"mcp_widget",expected_predecessor_checkpoint:checkpoint};
    }
    function setDecisionField(item, field, value) {
      const decision = item && decisionFor(item.id);
      if (!decision) return;
      if (field === "requested_documents") decision[field] = String(value || "").split(/\r?\n/).map(entry => entry.trim()).filter(Boolean);
      else decision[field] = String(value || "");
      persistWidgetState();
      renderProgress();
    }

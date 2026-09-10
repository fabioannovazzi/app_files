/**
 * Acquire an ECONS review using saved, reviewed Playwright phase capabilities.
 * Code owns exact identity, exclusions, counts and persistence. Optional processing
 * delegates to reviewed phases and model-reviewed treatment; acquisition alone
 * never changes a mapping or posts.
 */
import { execFile } from "node:child_process";
import { mkdir, realpath, stat, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import { canonicalJson, executeCapability, sha256Text } from "./capability_runtime.mjs";

import { processEconsInvoice, validateEconsProcessingProfile } from "./econs_processing.mjs";

const runFile = promisify(execFile);
const scripts = dirname(fileURLToPath(import.meta.url));
const PHASES = ["companies", "invoices", "detail"];
const FIELDS = {
  companies: ["company-code", "nightly"],
  company: ["company-code"],
  invoices: ["invoice-id", "invoice-number", "supplier", "status"],
  invoice: ["company-code", "invoice-id", "invoice-number", "supplier", "status"],
  lines: ["line-id", "description", "account", "vat-code", "amount"],
};
const OUTPUTS = {
  companies: { companies: "record_set", "company-count": "scalar" },
  invoices: { company: "record", invoices: "record_set", "invoice-count": "scalar" },
  detail: { invoice: "record", lines: "record_set", "line-count": "scalar" },
};
const INPUTS = { companies: [], invoices: ["company-code"], detail: ["company-code", "invoice-id", "invoice-number"] };

class EconsReviewError extends Error {}

function requireCondition(condition, code) {
  if (!condition) throw new EconsReviewError(code);
}

function sameKeys(value, keys) {
  return value != null && !Array.isArray(value) && typeof value === "object" &&
    Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));
}

/** Check only executable shape; the host model must verify the actual UI binding. */
export function validateEconsProfile(profile) {
  requireCondition(sameKeys(profile, ["schema_version", "phases"]) &&
    profile.schema_version === "econs-review-profile/v1" && sameKeys(profile.phases, PHASES), "invalid_econs_profile");
  let origins;
  for (const name of PHASES) {
    const phase = profile.phases[name];
    requireCondition(["discovered", "validated_local"].includes(phase?.status), "phase_requires_reviewed_discovery");
    const currentOrigins = canonicalJson([...phase.site.allowed_origins].sort());
    origins ??= currentOrigins;
    requireCondition(currentOrigins === origins, "phase_origins_must_match");
    requireCondition(phase.inputs.length === INPUTS[name].length &&
      INPUTS[name].every((key) => phase.inputs.some((input) => input.name === key && input.required && input.type === "text")), "invalid_phase_inputs");
    const declarations = Object.fromEntries(phase.outputs.map((output) => [output.name, output]));
    requireCondition(phase.outputs.length === Object.keys(OUTPUTS[name]).length && sameKeys(declarations, Object.keys(OUTPUTS[name])), "invalid_phase_outputs");
    for (const [key, type] of Object.entries(OUTPUTS[name])) {
      const output = declarations[key];
      requireCondition(output.type === type && output.delivery === "model_and_artifact", "invalid_phase_output_delivery");
      if (FIELDS[key]) requireCondition(output.fields.length === FIELDS[key].length &&
        FIELDS[key].every((field) => output.fields.some((item) => item.name === field)), "invalid_phase_fields");
    }
    for (const milestone of phase.milestones) {
      for (const action of milestone.actions) {
        requireCondition(["read_only", "reversible"].includes(action.effect) && action.confirmation === "none" &&
          ["goto", "wait_for", "click", "extract"].includes(action.operation), "review_phase_must_not_write");
      }
    }
  }
}

function records(value, fields, identity) {
  requireCondition(Array.isArray(value), "missing_record_population");
  const seen = new Set();
  for (const item of value) {
    requireCondition(sameKeys(item, fields), "unexpected_record_fields");
    for (const field of fields) {
      requireCondition(field === "nightly" ? typeof item[field] === "boolean" : (typeof item[field] === "string" || (fields === FIELDS.lines && field !== identity && item[field] === null)), "invalid_record_value");
      requireCondition(typeof item[field] !== "string" || item[field].length <= 10000, "field_exceeds_review_capacity");
    }
    requireCondition(item[identity].trim() && !seen.has(item[identity]), "missing_or_duplicate_identity");
    seen.add(item[identity]);
  }
  return value;
}

function exactPopulation(items, count) {
  // Exact counts detect a partial page, virtualized grid or silently truncated list.
  requireCondition(typeof count === "string" && /^\d+$/.test(count) && Number(count) === items.length, "incomplete_population");
}

async function privateDirectory(path) {
  requireCondition(isAbsolute(path), "absolute_private_directory_required");
  const parent = await realpath(dirname(path));
  for (let ancestor = parent; ; ancestor = dirname(ancestor)) {
    try {
      await stat(join(ancestor, ".git"));
      throw new Error("run_directory_must_be_outside_git");
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
    if (dirname(ancestor) === ancestor) break;
  }
  const directory = join(parent, path.slice(dirname(path).length + 1));
  await mkdir(directory, { mode: 0o700 });
  return directory;
}

async function writePrivate(path, value) {
  await writeFile(path, canonicalJson(value), { flag: "wx", mode: 0o600 });
}

function reviewEntry(company, item, id) {
  return {
    id, document: `${company} · ${item["invoice-number"]} · ${item.supplier}`,
    action: "Preparare la revisione della fattura passiva",
    reason: "Acquisizione da ECONS; il trattamento contabile resta da valutare.",
    status: "pending", proposed: [], actual: [],
    evidence: [{ label: "Stato ECONS", value: item.status || "Non disponibile", source: "Elenco fatture passive" }],
    outcome: "Dettaglio non ancora acquisito. Nessuna contabilizzazione.",
    question: "", posting_reference: "", correction_of: "",
  };
}

/**
 * Run the read-only acquisition to a saved review. Reuse the profile on each run;
 * use a fresh directory. A failed run retains every earlier invoice and receipt.
 * pythonExecutable is the explicit managed interpreter, never PATH/default Python.
 */
export async function collectEconsReview({ tab, profile, excludedCompanyCodes,
  runDirectory, pythonExecutable, maxCompanies = 50, maxInvoices = 200, environment = {}, processing = null }) {
  profile = structuredClone(profile);
  validateEconsProfile(profile);
  if (processing) {
    processing = { ...processing, profile: structuredClone(processing.profile) };
    validateEconsProcessingProfile(processing.profile);
    requireCondition(canonicalJson([...processing.profile.phases.post.site.allowed_origins].sort()) ===
      canonicalJson([...profile.phases.detail.site.allowed_origins].sort()), "processing_acquisition_origins_must_match");
    requireCondition([processing.classifyInvoices, processing.reviewJournal, processing.approvePosting].every((callback) => typeof callback === "function"), "model_review_callbacks_required");
  }
  requireCondition(Array.isArray(excludedCompanyCodes) && excludedCompanyCodes.every((code) => typeof code === "string" && code.trim()), "explicit_exclusion_list_required");
  excludedCompanyCodes = [...excludedCompanyCodes];
  requireCondition(isAbsolute(pythonExecutable ?? ""), "managed_python_required");
  requireCondition(Number.isInteger(maxCompanies) && maxCompanies > 0 && maxCompanies <= 500 &&
    Number.isInteger(maxInvoices) && maxInvoices > 0 && maxInvoices <= 1000, "invalid_batch_limits");
  requireCondition(typeof runDirectory === "string" && isAbsolute(runDirectory), "absolute_private_directory_required");
  const directory = await privateDirectory(runDirectory);
  let revision = 0;
  let phaseNumber = 0;
  let acquired = 0;
  let activeEntry = null;
  let failure = null;
  const receipts = [];
  const selection = [];
  const companyReviews = new Map();
  const review = {
    schema_version: "browser-batch-review/v1", batch_id: "econs-review",
    title: processing ? "Fatture passive ECONS elaborate" : "Fatture passive ECONS da rivedere",
    scope: (processing ? "Elaborazione con revisione del modello e autorizzazione alla registrazione. " : "") + "Ditte con sincronizzazione notturna, escluse quelle nella lista locale. Acquisizione completa e rapporto persistente per cliente. Il totale resta sconosciuto finché la raccolta non è completa.",
    status: "paused", expected_items: null, entries: [], reviews: [],
  };
  async function python(script, args) {
    // Fixed local scripts and argv; no shell, package installation or external API.
    await runFile(pythonExecutable, [join(scripts, script), ...args], { maxBuffer: 1024 * 1024 });
  }
  async function save() {
    const input = join(directory, `review-input-${revision + 1}.json`);
    await writePrivate(input, review);
    await python("batch_review.py", ["save", join(directory, "review"), "--input", input, "--expected-revision", String(revision)]);
    revision += 1;
    for (const [code, state] of companyReviews) {
      const clientReview = { ...review, batch_id: state.id, title: `Fatture passive · cliente ${code}`,
        expected_items: state.count, entries: review.entries.filter((entry) => state.ids.has(entry.id)), reviews: [] };
      const clientInput = join(directory, `${state.id}-input-${state.revision + 1}.json`);
      await writePrivate(clientInput, clientReview);
      await python("batch_review.py", ["save", join(directory, state.id), "--input", clientInput, "--expected-revision", String(state.revision)]);
      state.revision += 1;
    }
  }
  async function phase(name, inputs) {
    phaseNumber += 1;
    let result;
    try {
      result = await executeCapability({ tab, capability: profile.phases[name], inputs,
        runDirectory: join(directory, `phase-${phaseNumber}`), runId: `econs-${name}-${phaseNumber}`, environment });
    } catch (error) {
      if (!error.runSummary) throw error;
      result = error.runSummary;
    }
    await writePrivate(join(directory, `phase-${phaseNumber}`, "summary.private.json"), result);
    receipts.push(result.receipt_path);
    requireCondition(result.result === "passed", `phase_${name}_failed`);
    return result.delivered_outputs;
  }
  await writePrivate(join(directory, "profile.json"), profile);
  await writePrivate(join(directory, "selection.json"), { excluded_company_codes: excludedCompanyCodes, max_companies: maxCompanies, max_invoices: maxInvoices });
  // Validate every phase before the first browser operation, not halfway through.
  await python("check_installation.py", []);
  await python("check_dependencies.py", []);
  for (const name of PHASES) {
    const path = join(directory, `${name}.capability.json`);
    await writePrivate(path, profile.phases[name]);
    await python("capability_pipeline.py", ["validate", path, "--kind", "capability"]);
  }
  if (processing) {
    await writePrivate(join(directory, "processing-profile.json"), processing.profile);
    for (const [name, capability] of Object.entries(processing.profile.phases)) {
      const path = join(directory, `processing-${name}.capability.json`);
      await writePrivate(path, capability);
      await python("capability_pipeline.py", ["validate", path, "--kind", "capability"]);
    }
  }
  await save();
  try {
    const companyOutput = await phase("companies", {});
    const companies = records(companyOutput.companies, FIELDS.companies, "company-code");
    exactPopulation(companies, companyOutput["company-count"]);
    const excluded = new Set(excludedCompanyCodes);
    const selected = companies.filter((company) => company.nightly && !excluded.has(company["company-code"]));
    requireCondition(selected.length <= maxCompanies, "company_limit_exceeded");
    for (const company of selected) {
      const output = await phase("invoices", { "company-code": company["company-code"] });
      requireCondition(sameKeys(output.company, FIELDS.company) && output.company["company-code"] === company["company-code"], "wrong_company");
      const invoices = records(output.invoices, FIELDS.invoices, "invoice-id");
      exactPopulation(invoices, output["invoice-count"]);
      requireCondition(review.entries.length + invoices.length <= maxInvoices, "invoice_limit_exceeded");
      selection.push({ company_code: company["company-code"], invoice_count: invoices.length });
      const pending = invoices.map((invoice) => {
        const id = `invoice-${sha256Text(canonicalJson([company["company-code"], invoice["invoice-id"]])).slice(0, 24)}`;
        const entry = reviewEntry(company["company-code"], invoice, id);
        review.entries.push(entry);
        return { invoice, entry };
      });
      companyReviews.set(company["company-code"], { id: `client-${sha256Text(company["company-code"]).slice(0, 24)}`,
        ids: new Set(pending.map(({ entry }) => entry.id)), count: invoices.length, revision: 0 });
      await save();
      let redIds = new Set();
      if (processing) {
        const decision = await processing.classifyInvoices(structuredClone({ company, invoices }));
        requireCondition(decision?.company_code === company["company-code"] && typeof decision.reason === "string" && decision.reason.trim() &&
          Array.isArray(decision.red_invoice_ids) && new Set(decision.red_invoice_ids).size === decision.red_invoice_ids.length &&
          decision.red_invoice_ids.every((id) => invoices.some((item) => item["invoice-id"] === id)), "explicit_model_queue_classification_required");
        redIds = new Set(decision.red_invoice_ids);
        await writePrivate(join(directory, `queue-${sha256Text(company["company-code"]).slice(0, 24)}.json`), decision);
      }
      let consecutiveRed = 0;
      let stopCompany = false;
      for (const { invoice, entry } of pending) {
        if (processing) {
          const red = redIds.has(invoice["invoice-id"]);
          consecutiveRed = red ? consecutiveRed + 1 : 0;
          stopCompany ||= consecutiveRed > 2;
          if (red || stopCompany) {
            entry.status = "set_aside";
            entry.outcome = stopCompany ? "Ditta sospesa dopo oltre due rossi consecutivi." : "Fattura rossa esclusa dalla registrazione secondo la classificazione del modello.";
            entry.question = "Rivedere la fattura e riprendere il cliente dopo aver risolto le eccezioni.";
            await save();
            continue;
          }
        }
        activeEntry = entry;
        let detail = await phase("detail", { "company-code": company["company-code"], "invoice-id": invoice["invoice-id"], "invoice-number": invoice["invoice-number"] });
        requireCondition(sameKeys(detail.invoice, FIELDS.invoice) && detail.invoice["company-code"] === company["company-code"] &&
          FIELDS.invoices.every((field) => detail.invoice[field] === invoice[field]), "invoice_identity_or_state_changed");
        const lines = records(detail.lines, FIELDS.lines, "line-id");
        exactPopulation(lines, detail["line-count"]);
        requireCondition(lines.length > 0 && lines.length <= 90, "missing_or_excessive_invoice_lines");
        const missing = [];
        for (const line of lines) {
          for (const field of ["description", "account", "vat-code", "amount"]) {
            const source = `ECONS · riga ${line["line-id"]} · ${field}`;
            entry.evidence.push({ label: `${line["line-id"]} · ${field}`, value: (line[field] ?? "").trim() ? line[field] : "Non disponibile", source });
            if (!(line[field] ?? "").trim()) missing.push(`${line["line-id"]}: ${field}`);
          }
        }
        entry.outcome = "Dati e mappature esistenti acquisiti. Nessuna contabilizzazione e nessuna approvazione contabile automatica.";
        if (missing.length) {
          entry.status = "set_aside";
          entry.question = `Verificare i campi mancanti: ${missing.join(", ")}`;
        }
        acquired += 1;
        await save();
        if (processing) {
          await processEconsInvoice({ tab, profile: processing.profile,
            invoice: { "company-code": company["company-code"], ...invoice }, detail, entry,
            readDetail: () => phase("detail", { "company-code": company["company-code"], "invoice-id": invoice["invoice-id"], "invoice-number": invoice["invoice-number"] }),
            phaseDirectory: async (name) => join(directory, `process-${entry.id}-${name}`),
            save, reviewJournal: processing.reviewJournal, approvePosting: processing.approvePosting, environment });
        }
        activeEntry = null;
      }
    }
    review.expected_items = review.entries.length;
  } catch (error) {
    failure = { category: "acquisition_incomplete", reason_code: error instanceof EconsReviewError ? error.message : "runtime_or_persistence_failure", detail_sha256: sha256Text(String(error)) };
    if (activeEntry) {
      activeEntry.status = processing ? "unverified" : "failed";
      activeEntry.question = "Riprendere l'acquisizione del dettaglio dopo aver verificato identità, campi e controlli ECONS.";
      activeEntry.outcome = processing ? "Elaborazione interrotta: verificare lo stato esterno e le ricevute prima di ripetere azioni." : "Acquisizione interrotta; nessuna contabilizzazione.";
    }
  }
  await save();
  const summary = {
    schema_version: "econs-review-acquisition/v1", status: failure ? "partial" : processing ? "processed" : "acquired",
    profile_sha256: sha256Text(canonicalJson(profile)), acquired_invoices: acquired,
    pending_review: review.entries.filter((entry) => entry.status === "pending").length,
    exceptions: review.entries.filter((entry) => entry.status !== "pending").length,
    expected_items: review.expected_items,
    posting_actions: processing ? null : 0,
    completed: review.entries.filter((entry) => entry.status === "completed").length,
    client_reviews: [...companyReviews.values()].map((state) => join(directory, state.id, `review-${String(state.revision).padStart(4, "0")}.html`)),
    receipts,
    review_path: join(directory, "review", `review-${String(revision).padStart(4, "0")}.html`),
    review_directory: join(directory, "review"), error: failure,
  };
  await writePrivate(join(directory, "acquisition.json"), { ...summary, selected_companies: selection });
  return summary;
}

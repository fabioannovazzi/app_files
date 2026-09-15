/** Connect a persisted process attempt to the existing capability executor.
 * Meaning, result review and sanitization belong to the current host model.
 * This wrapper records actual local timing and never estimates model usage.
 */
import { open, readFile, lstat, rename } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { performance } from "node:perf_hooks";
import { homedir, hostname, platform } from "node:os";
import {
  canonicalJson, executeCapability, executionContractSha256, sha256Text,
} from "./capability_runtime.mjs";

async function safePath(path) {
  for (let current = resolve(path); ; current = dirname(current)) {
    try {
      if ((await lstat(current)).isSymbolicLink()) throw new Error("unsafe_process_path");
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
    if (dirname(current) === current) break;
  }
  return resolve(path);
}

async function writeExclusive(path, text) {
  await safePath(path);
  const stream = await open(path, "wx", 0o600);
  try { await stream.writeFile(text, "utf8"); } finally { await stream.close(); }
}

const unavailable = () => ({ value: null, source: null, missing_reason: "host_does_not_expose_measurement" });

function measurements(values = {}) {
  const result = { model: unavailable(), input_tokens: unavailable(), output_tokens: unavailable() };
  for (const [name, item] of Object.entries(values)) {
    if (!(name in result) || item == null || typeof item !== "object" ||
        Object.keys(item).sort().join() !== "missing_reason,source,value") {
      throw new Error("invalid_host_measurements");
    }
    if (item.value == null) {
      if (item.source !== null || typeof item.missing_reason !== "string" || !item.missing_reason.trim() || item.missing_reason.length > 160) throw new Error("missing_measurement_reason_required");
    } else if (typeof item.source !== "string" || !item.source.trim() || item.source.length > 160 || item.missing_reason !== null ||
      (name === "model" ? typeof item.value !== "string" || item.value.length > 128 : !Number.isSafeInteger(item.value) || item.value < 0)) {
      throw new Error("invalid_measured_value");
    }
    result[name] = item;
  }
  return result;
}

/** Run one prepared attempt once. Read actual host documentation before declaring live mode. */
export async function executeProcess({ attemptDirectory, tab, inputs = {}, currentHost,
  approvedConsequentialActions = [], recoveryHandler = null, downloadDirectory,
  hostMeasurements = {},
}) {
  const directory = await safePath(attemptDirectory);
  const plan = JSON.parse(await readFile(join(directory, "attempt.json"), "utf8"));
  if (plan.schema_version !== "browser-process-attempt/v1" ||
      !/^attempt-[a-f0-9]{32}$/.test(plan.attempt_id) ||
      !/^process-[a-f0-9]{32}$/.test(plan.process_id) ||
      !["test", "use"].includes(plan.kind)) throw new Error("invalid_execution_attempt");
  // Exclusive acquisition prevents retrying an uncertain consequential run.
  await writeExclusive(join(directory, "execution.started.json"), canonicalJson({ attempt_id: plan.attempt_id, started_at: new Date().toISOString() }));
  const start = performance.now();
  const startedAt = new Date().toISOString();
  let summary = null;
  let reason = null;
  let failureHash = null;
  let telemetry = measurements();
  try {
    telemetry = measurements(hostMeasurements);
    if (plan.blocked_reason != null) throw new Error(plan.blocked_reason);
    if (plan.host_fingerprint !== sha256Text(canonicalJson({ system: platform(), machine: hostname(), home: homedir() }))) throw new Error("host_changed_since_preparation");
    if (canonicalJson(plan.host) !== canonicalJson(currentHost)) throw new Error("host_changed_since_preparation");
    if (!currentHost.browser_control || !currentHost.persistent_node || !currentHost.local_files || !tab?.playwright || typeof tab.goto !== "function") throw new Error("host_capabilities_unavailable");
    const implementation = plan.implementation;
    const capability = JSON.parse(await readFile(await safePath(implementation.path), "utf8"));
    if (sha256Text(canonicalJson(capability)) !== implementation.capability_sha256 ||
        executionContractSha256(capability) !== implementation.execution_contract_sha256 ||
        capability.capability_id !== implementation.capability_id || capability.version !== implementation.version) throw new Error("registered_capability_changed");
    summary = await executeCapability({ tab, capability, inputs,
      runDirectory: join(directory, "run"), runId: plan.attempt_id,
      approvedConsequentialActions, recoveryHandler,
      environment: currentHost,
      ...(downloadDirectory === undefined ? {} : { downloadDirectory }),
    });
  } catch (error) {
    failureHash = sha256Text(error instanceof Error ? error.message : String(error));
    summary = error.runSummary ?? null;
    // Raw browser errors can contain private URLs or values; retain only a hash.
    const safeReasons = new Set(["implementation_unavailable", "qualification_required", "host_capabilities_unavailable", "host_changed_since_preparation", "registered_capability_changed", "invalid_host_measurements", "missing_measurement_reason_required", "invalid_measured_value"]);
    reason = safeReasons.has(error.message) ? error.message : "executor_failed";
  }
  const receiptBytes = summary == null ? null : await readFile(join(directory, "run", "run.receipt.json"), "utf8");
  const evidence = {
    schema_version: "browser-process-execution/v1", process_id: plan.process_id,
    attempt_id: plan.attempt_id, plan_sha256: sha256Text(canonicalJson(plan)),
    started_at: startedAt, finished_at: new Date().toISOString(),
    elapsed_ms: Math.max(0, Math.round(performance.now() - start)),
    elapsed_source: "local_monotonic_clock_wrapper_including_preflight",
    execution_mode: plan.host.execution_mode,
    result: summary?.result ?? "blocked", missing_reason: reason,
    receipt_sha256: receiptBytes == null ? null : sha256Text(receiptBytes),
    outputs: summary?.outputs ?? [], recovery_used: (summary?.recovery_proposal_count ?? 0) > 0,
    error: summary?.error ?? null, failure_detail_sha256: failureHash, measurements: telemetry,
  };
  await writeExclusive(join(directory, "execution.json"), canonicalJson(evidence));
  const lines = [
    `# ${plan.description.process.name}`, "",
    `Processo: ${plan.process_id}`, `Tentativo: ${plan.attempt_id} · ${plan.kind}`,
    `Risultato: ${evidence.result}`, `Ambiente dichiarato: ${evidence.execution_mode}`,
    `Obiettivo: ${plan.description.process.objective}`,
    `Verifica attesa: ${plan.description.end_condition}`, "", "## Risultati verificabili",
    ...evidence.outputs.map(o => `- ${o.name}: ${o.record_count} · SHA-256 ${o.sha256}`),
    ...(summary == null ? ["- Nessun output verificato disponibile."] : [`- [Ricevuta locale](${summary.receipt_path})`, `- [Output locali](${summary.outputs_path})`]),
    "", "## Misure e informazioni mancanti",
    `Durata misurata: ${evidence.elapsed_ms} ms (tempo locale, inclusa preparazione).`,
    ...Object.entries(telemetry).map(([name, item]) => `${name}: ${item.value ?? "non disponibile"} · ${item.source ?? item.missing_reason}`),
    `Motivo: ${reason ?? "nessun errore tecnico; verificare la correttezza professionale del risultato"}`,
    "", "## Prossimo passo",
    "Verificare gli output e salvare la revisione. Un risultato incompleto conserva le prove per lo stesso processo.",
    "Nessun CR è stato inviato da questo esecutore. Vera prepara e trasmette il riepilogo tecnico solo entro l’autorizzazione ricevuta.",
    "I test simulati non qualificano l’automazione sul sito reale. Riprendere dal catalogo locale anche in una nuova conversazione.",
  ];
  const temporaryReport = join(directory, "REPORT.execution.tmp");
  await writeExclusive(temporaryReport, `${lines.join("\n")}\n`);
  await safePath(join(directory, "REPORT.md"));
  await rename(temporaryReport, join(directory, "REPORT.md"));
  return { process_id: plan.process_id, attempt_id: plan.attempt_id,
    result: evidence.result, execution_mode: evidence.execution_mode,
    report_path: join(directory, "REPORT.md"), evidence_path: join(directory, "execution.json"),
    summary, missing_reason: reason };
}

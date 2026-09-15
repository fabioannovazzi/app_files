/** Local ECONS setup discovery for a new conversation. No browser or network I/O.
 * IDs, hashes and paths are mechanical checks; saved setup grants no authority.
 */
import { randomUUID } from "node:crypto";
import { lstat, mkdir, open, readFile, readdir, rename, unlink, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { canonicalJson, sha256Text } from "./capability_runtime.mjs";
import { validateEconsProfile } from "./econs_review.mjs";
import { validateEconsProcessingProfile } from "./econs_processing.mjs";

const SCHEMA = "econs-saved-setup/v1";
const ID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const procedurePath = fileURLToPath(new URL("../references/passive-invoice-procedure.md", import.meta.url));
function need(value, code) { if (!value) throw new Error(code); }

export function defaultEconsSetupDirectory() {
  return process.platform === "win32"
    ? join(process.env.LOCALAPPDATA || join(homedir(), "AppData", "Local"), "vera", "econs")
    : join(homedir(), ".local", "share", "vera", "econs");
}

async function privatePath(path) {
  need(typeof path === "string" && isAbsolute(path), "absolute_setup_path_required");
  for (let current = resolve(path); ; current = dirname(current)) {
    try {
      need(!(await lstat(current)).isSymbolicLink(), "setup_symlink_not_allowed");
    } catch (error) { if (!["ENOENT", "ENOTDIR"].includes(error.code)) throw error; }
    try {
      await lstat(join(current, ".git"));
      throw new Error("setup_must_be_outside_git");
    } catch (error) { if (!["ENOENT", "ENOTDIR"].includes(error.code)) throw error; }
    if (dirname(current) === current) break;
  }
}

async function readRecord(path) {
  await privatePath(path);
  need((await lstat(path)).isFile(), "setup_must_be_regular_file");
  const record = JSON.parse(await readFile(path, "utf8"));
  need(record.schema_version === SCHEMA && record.payload &&
    record.sha256 === sha256Text(canonicalJson(record.payload)), "saved_setup_integrity_failed");
  need(ID.test(record.payload.id) && typeof record.payload.label === "string" &&
    (Array.isArray(record.payload.excludedCompanyCodes) ||
      record.payload.incomplete && record.payload.excludedCompanyCodes === null), "invalid_saved_setup");
  return record;
}

async function records(directory) {
  await privatePath(directory);
  let names;
  try { names = await readdir(directory); }
  catch (error) { if (error.code === "ENOENT") return []; throw error; }
  const files = names.filter((name) => name.endsWith(".json") && ID.test(name.slice(0, -5)));
  need(files.length <= 100, "too_many_saved_setups");
  const result = [];
  for (const name of files.sort()) {
    const record = await readRecord(join(directory, name));
    need(`${record.payload.id}.json` === name, "saved_setup_identity_changed");
    result.push(record);
  }
  return result;
}

/** Find only Vera's known local storage, never scan chats, Downloads or a disk. */
export async function loadEconsSetup({ directory = defaultEconsSetupDirectory(), setupId = null } = {}) {
  need(setupId === null || ID.test(setupId), "invalid_setup_id");
  const saved = await records(directory);
  const selected = setupId ? saved.find((record) => record.payload.id === setupId) : saved.length === 1 ? saved[0] : null;
  if (!selected) return {
    status: setupId ? "saved_setup_missing" : saved.length ? "choose_setup" : "setup_required",
    procedurePath,
    setups: saved.map(({ payload }) => ({ setupId: payload.id, label: payload.label })),
  };
  const payload = structuredClone(selected.payload);
  if (payload.incomplete) return { status: "setup_incomplete", procedurePath, ...payload, setupId: payload.id };
  if (payload.profile?.schema_version === "econs-review-profile/v1") return {
    status: "company_signal_update_required", procedurePath, ...payload, setupId: payload.id,
  };
  validateEconsProfile(payload.profile);
  if (payload.processingProfile) validateEconsProcessingProfile(payload.processingProfile);
  return { status: "saved_setup", procedurePath, ...payload,
    setupId: payload.id, previousRunDirectory: payload.lastRunDirectory,
    // The caller must reconcile any uncertain prior posting from these local
    // reports, and verify current account/client identity before new actions.
    executionAuthorized: false };
}

/** Save reviewed bindings automatically; immutable revisions survive updates. */
export async function saveEconsSetup({ profile, processingProfile = null, excludedCompanyCodes,
  lastRunDirectory = null, setupId = null, label = "TeamSystem ECONS",
  incomplete = false, pendingStep = null,
  directory = defaultEconsSetupDirectory() }) {
  need(typeof incomplete === "boolean", "invalid_setup_stage");
  if (incomplete) {
    need(profile?.schema_version === "econs-review-profile/v2" && profile.phases &&
      !Array.isArray(profile.phases) && Object.keys(profile.phases).every((name) => ["companies", "invoices", "detail"].includes(name)) &&
      typeof pendingStep === "string" && pendingStep.trim() && pendingStep.length <= 2000, "invalid_incomplete_setup");
  } else {
    validateEconsProfile(profile);
    if (processingProfile) validateEconsProcessingProfile(processingProfile);
  }
  need(incomplete && excludedCompanyCodes === null || Array.isArray(excludedCompanyCodes) &&
    excludedCompanyCodes.every((code) => typeof code === "string" && code.trim()), "invalid_studio_exclusions");
  need(typeof label === "string" && label.trim() && label.length <= 120, "invalid_setup_label");
  need(setupId === null || ID.test(setupId), "invalid_setup_id");
  await privatePath(directory);
  if (lastRunDirectory !== null) await privatePath(lastRunDirectory);
  const saved = await records(directory);
  const origins = canonicalJson([...(profile.phases.companies?.site?.allowed_origins ?? [])].sort());
  if (setupId === null) {
    const matches = saved.filter(({ payload }) => payload.label === label &&
      canonicalJson([...(payload.profile.phases.companies?.site?.allowed_origins ?? [])].sort()) === origins &&
      canonicalJson(payload.excludedCompanyCodes) === canonicalJson(excludedCompanyCodes));
    need(matches.length <= 1, "choose_setup_before_saving");
    setupId = matches[0]?.payload.id ?? randomUUID();
  }
  await mkdir(directory, { recursive: true, mode: 0o700 });
  const path = join(directory, `${setupId}.json`);
  const lockPath = join(directory, `${setupId}.lock`);
  const lock = await open(lockPath, "wx", 0o600);
  const temporary = join(directory, `${setupId}-${randomUUID()}.tmp`);
  try {
    // Read under the write lock so a concurrent read-only run cannot erase
    // processing bindings saved since the initial discovery.
    let previous = null;
    try { previous = await readRecord(path); }
    catch (error) { if (error.code !== "ENOENT") throw error; }
    // A review-only run must not erase already learned registration bindings.
    processingProfile ??= previous?.payload.processingProfile ?? null;
    if (processingProfile && !incomplete) {
      validateEconsProcessingProfile(processingProfile);
      need(canonicalJson([...processingProfile.phases.post.site.allowed_origins].sort()) === origins,
        "processing_acquisition_origins_must_match");
    }
    lastRunDirectory ??= previous?.payload.lastRunDirectory ?? null;
    const payload = { id: setupId, label, profile, processingProfile, excludedCompanyCodes,
      lastRunDirectory, incomplete, pendingStep: incomplete ? pendingStep : null };
    const sha256 = sha256Text(canonicalJson(payload));
    const record = { schema_version: SCHEMA, sha256, payload };
    const history = join(directory, setupId);
    await privatePath(history);
    await mkdir(history, { mode: 0o700, recursive: true });
    const bytes = canonicalJson(record);
    try { await writeFile(join(history, `${sha256}.json`), bytes, { flag: "wx", mode: 0o600 }); }
    catch (error) { if (error.code !== "EEXIST") throw error; }
    await writeFile(temporary, bytes, { flag: "wx", mode: 0o600 });
    await rename(temporary, path);
    return { setupId, setupPath: path };
  } finally {
    await lock.close();
    await unlink(lockPath);
    try { await unlink(temporary); } catch (error) { if (error.code !== "ENOENT") throw error; }
  }
}

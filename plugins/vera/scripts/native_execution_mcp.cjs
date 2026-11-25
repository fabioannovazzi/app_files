"use strict";

// The service owns persistent execution, not the restricted chat shell. Verify
// the bootstrap before importing it, then pin all owned code for this process.
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { createHash, randomUUID } = require("node:crypto");
const { spawn } = require("node:child_process");
function launch() {
const root = path.resolve(__dirname, "..");
const settingsIndex = process.argv.indexOf("--settings");
const settings = { host_session: randomUUID(),
  host: fs.existsSync(path.join(root, ".codex-plugin/plugin.json")) ? "codex" : "cowork",
  ...(settingsIndex < 0 ? {} : JSON.parse(fs.readFileSync(process.argv[settingsIndex + 1], "utf8"))) };
const timeoutIndex = process.argv.indexOf("--report-startup-timeout");
const timeoutMs = timeoutIndex < 0 ? null : Number(process.argv[timeoutIndex + 1]);
if (timeoutMs !== null && (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1))
  throw new Error("Invalid Vera startup timeout duration");
const indexPath = path.join(root, "execution-files.json");
const development = fs.existsSync(path.resolve(root, "../../.git")) &&
  fs.existsSync(path.resolve(root, "../_shared"));
const index = fs.existsSync(indexPath) ? JSON.parse(fs.readFileSync(indexPath, "utf8")).files : null;
if (!index && !development) throw new Error("Vera execution build index is unavailable");
function checked(relative) {
  const file = path.join(root, relative), info = fs.lstatSync(file);
  if (!info.isFile() || info.isSymbolicLink()) throw new Error(`Invalid execution bootstrap: ${relative}`);
  const bytes = fs.readFileSync(file);
  if (index && createHash("sha256").update(bytes).digest("hex") !== index[relative])
    throw new Error(`Execution bootstrap does not match its build index: ${relative}`);
  return bytes;
}
checked("scripts/native_execution_mcp.cjs");
let python = "python3";
let prefix = [];
if (process.platform === "win32") {
  checked("scripts/windows_python.cjs");
  ({ executable: python, prefix } = require("./windows_python.cjs").windowsPython());
} else {
  const runtime = process.env.MPARANZA_RUNTIME_ROOT || path.join(os.homedir(), ".local/share/mparanza/runtime");
  const managed = path.join(runtime, "venv", "bin", "python");
  if (fs.existsSync(managed)) python = managed;
}
const bootstrap = fs.mkdtempSync(path.join(os.tmpdir(), "vera-execution-bootstrap-"));
// One Python process owns verification, the service and its live workers.
// A short-lived preparer must not delete code before the service can use it.
const program = [
  "import json,os,runpy,sys,signal",
  // A signal handler must never acquire an Event/Condition mutex: a repeated
  // signal can reenter it while that same thread holds the nonreentrant lock.
  "shutdown={'requested':False}",
  "for sig in (signal.SIGTERM,signal.SIGINT): signal.signal(sig,lambda *_: shutdown.__setitem__('requested',True))",
  "from pathlib import Path",
  "sys.path.insert(0,sys.argv[1])",
  "from verified_execution import prepare_execution_root,release_execution_root,own_execution_root,recover_abandoned_windows_bootstraps,execution_package_id,report_preparation_failure",
  "bootstrap=Path(sys.argv[1]).resolve()",
  "os.chdir(bootstrap.parent)",
  "own_execution_root(bootstrap)",
  "snapshot=None",
  "try:",
  "    if sys.argv[4]:",
  "        report_preparation_failure(Path(sys.argv[2]),None,TimeoutError(),stage='veraExecution.initialize',technical_code='execution.initialize-timeout',settings=json.loads(sys.argv[3]),elapsed_ms=int(sys.argv[4]))",
  "    else:",
  "        if os.name=='nt': recover_abandoned_windows_bootstraps()",
  "        snapshot=prepare_execution_root(Path(sys.argv[2]),None,snapshot=True,shared=True)",
  "        os.chdir(snapshot)",
  "        os.environ['VERA_EXECUTION_PACKAGE_ID']=execution_package_id(snapshot) or 'development'",
  "        script=snapshot/'scripts/native_execution.py'",
  "        sys.argv=[str(script), '--settings-json', sys.argv[3]]",
  "        runpy.run_path(str(script),run_name='__main__',init_globals={'_SHUTDOWN':shutdown})",
  "finally:",
  "    if snapshot is not None: release_execution_root(snapshot)",
  "    release_execution_root(bootstrap)",
].join("\n");
function cleanupBootstrap() {
  try { fs.rmSync(bootstrap, { recursive: true, force: true }); }
  catch (error) { process.stderr.write(`Vera bootstrap cleanup pending: ${error.message}\n`); }
}
try {
  for (const name of ["verified_execution.py", "reporting_product.py"])
    fs.writeFileSync(path.join(bootstrap, name), checked(`scripts/${name}`), { mode: 0o600 });
  // The transport parent must release the replaceable installation directory
  // too: Windows prevents its removal while any process keeps it as cwd.
  process.chdir(os.tmpdir());
  const child = spawn(python, [...prefix, "-X", "utf8", "-I", "-B", "-c", program, bootstrap, root, JSON.stringify(settings), timeoutMs?.toString() || ""],
    { cwd: bootstrap, env: process.env, stdio: "inherit" });
  // A host stop closes this transport, not the detached professional jobs.
  // Keep the owner alive until its workers release the leased code.
  for (const sig of ["SIGTERM", "SIGINT"])
    process.on(sig, () => { if (child.exitCode === null) child.kill(sig); });
  let spawnFailed = false;
  child.on("error", error => { spawnFailed = true; process.stderr.write(`${error.message}\n`); });
  child.on("close", code => { cleanupBootstrap(); process.exitCode = spawnFailed ? 1 : code ?? 1; });
} catch (error) {
  cleanupBootstrap();
  throw error;
}

}
module.exports = { launch };
if (require.main === module) launch();

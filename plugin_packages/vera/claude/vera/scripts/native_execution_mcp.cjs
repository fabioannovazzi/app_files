"use strict";

// The service owns persistent execution, not the restricted chat shell. Verify
// the bootstrap before importing it, then pin all owned code for this process.
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { createHash } = require("node:crypto");
const { spawn } = require("node:child_process");
function launch(mode = "native", args = []) {
const root = path.resolve(__dirname, "..");
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
if (mode === "component") checked("scripts/run_component_mcp.cjs");
if (mode === "service") checked("scripts/run_service_mcp.cjs");
const bootstrap = fs.mkdtempSync(path.join(os.tmpdir(), "vera-execution-bootstrap-"));
const runtime = process.env.MPARANZA_RUNTIME_ROOT || (process.platform === "win32"
  ? path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData/Local"), "mpr")
  : path.join(os.homedir(), ".local/share/mparanza/runtime"));
const managed = path.join(runtime, "venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const python = fs.existsSync(managed) ? managed : (process.platform === "win32" ? "python" : "python3");
// One Python process owns verification, the service and its live workers.
// A short-lived preparer must not delete code before the service can use it.
const program = [
  "import os,runpy,sys,signal,subprocess",
  // A signal handler must never acquire an Event/Condition mutex: a repeated
  // signal can reenter it while that same thread holds the nonreentrant lock.
  "shutdown={'requested':False}",
  "for sig in (signal.SIGTERM,signal.SIGINT): signal.signal(sig,lambda *_: shutdown.__setitem__('requested',True))",
  "from pathlib import Path",
  "sys.path.insert(0,sys.argv[1])",
  "from verified_execution import prepare_execution_root,release_execution_root,own_execution_root,recover_abandoned_execution_roots,execution_lease_fds,execution_package_id",
  "bootstrap=Path(sys.argv[1]).resolve()",
  "own_execution_root(bootstrap)",
  "snapshot=None",
  "try:",
  "    snapshot=prepare_execution_root(Path(sys.argv[2]),None,snapshot=True,shared=True)",
  "    os.chdir(snapshot)",
  "    os.environ['VERA_EXECUTION_PACKAGE_ID']=execution_package_id(snapshot) or 'development'",
  "    if sys.argv[3]=='component':",
  "        gateway=runpy.run_path(str(snapshot/'scripts/component_gateway.py'))",
  "        sys.path.insert(0,str(snapshot/'scripts'))",
  "        raise SystemExit(gateway['serve'](snapshot,sys.argv[4],sys.argv[5],shutdown))",
  "    elif sys.argv[3]=='service':",
  "        entry=sys.argv[5]",
  "        if entry not in {'scripts/course_chat_mcp.cjs','mcp/workspace.cjs','mcp/studio-work.cjs','mcp/research-sources.cjs','scripts/incident_host_mcp.cjs'}: raise ValueError('Unknown Vera product service')",
  "        fds=execution_lease_fds(snapshot) if os.name=='posix' else ()",
  "        child=subprocess.Popen([sys.argv[4],str(snapshot/entry),*sys.argv[6:]],cwd=snapshot,**({'pass_fds':fds} if os.name=='posix' else {}))",
  "        while child.poll() is None:",
  "            if shutdown['requested']: child.terminate()",
  "            try: child.wait(timeout=0.2)",
  "            except subprocess.TimeoutExpired: pass",
  "        raise SystemExit(child.returncode)",
  "    else:",
  "        script=snapshot/'scripts/native_execution.py'",
  "        sys.argv=[str(script)]",
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
  const child = spawn(python, ["-I", "-B", "-c", program, bootstrap, root, mode, process.execPath, ...args],
    { cwd: bootstrap, env: process.env, stdio: "inherit" });
  // A host stop closes this transport, not the detached professional jobs.
  // Keep the owner alive until its workers release the leased code.
  for (const sig of ["SIGTERM", "SIGINT"])
    process.on(sig, () => { if (child.exitCode === null) child.kill(sig); });
  child.on("error", error => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
  child.on("close", code => { cleanupBootstrap(); process.exitCode = code ?? 1; });
} catch (error) {
  cleanupBootstrap();
  throw error;
}

}
module.exports = { launch };
if (require.main === module) launch();

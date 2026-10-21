"use strict";

// The service owns persistent execution, not the restricted chat shell. Verify
// the bootstrap before importing it, then pin all owned code for this process.
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { createHash } = require("node:crypto");
const { spawn } = require("node:child_process");
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
const bootstrap = fs.mkdtempSync(path.join(os.tmpdir(), "vera-execution-bootstrap-"));
const runtime = process.env.MPARANZA_RUNTIME_ROOT || (process.platform === "win32"
  ? path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData/Local"), "mpr")
  : path.join(os.homedir(), ".local/share/mparanza/runtime"));
const managed = path.join(runtime, "venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const python = fs.existsSync(managed) ? managed : (process.platform === "win32" ? "python" : "python3");
// One Python process owns verification, the service and its live workers.
// A short-lived preparer must not delete code before the service can use it.
const program = [
  "import runpy,sys",
  "from pathlib import Path",
  "sys.path.insert(0,sys.argv[1])",
  "from verified_execution import prepare_execution_root,release_execution_root",
  "snapshot=prepare_execution_root(Path(sys.argv[2]),None,snapshot=True)",
  "script=snapshot/'scripts/native_execution.py'",
  "sys.argv=[str(script)]",
  "try:",
  "    runpy.run_path(str(script),run_name='__main__')",
  "finally:",
  "    release_execution_root(snapshot)",
].join("\n");
function cleanupBootstrap() {
  try { fs.rmSync(bootstrap, { recursive: true, force: true }); }
  catch (error) { process.stderr.write(`Vera bootstrap cleanup pending: ${error.message}\n`); }
}
try {
  for (const name of ["verified_execution.py", "reporting_product.py"])
    fs.writeFileSync(path.join(bootstrap, name), checked(`scripts/${name}`), { mode: 0o600 });
  const child = spawn(python, ["-I", "-B", "-c", program, bootstrap, root],
    { cwd: bootstrap, env: process.env, stdio: "inherit" });
  child.on("error", error => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
  child.on("close", code => { cleanupBootstrap(); process.exitCode = code ?? 1; });
} catch (error) {
  cleanupBootstrap();
  throw error;
}

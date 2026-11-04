"use strict";
// Reuse the installed, user-scoped Python runtime; never install at invocation.
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");
const root = path.resolve(__dirname, "..");
const runtime = process.env.MPARANZA_RUNTIME_ROOT || (process.platform === "win32"
  ? path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData/Local"), "mpr")
  : path.join(os.homedir(), ".local/share/mparanza/runtime"));
const managed = path.join(runtime, "venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const python = process.env.LUCIA_MATTER_PYTHON || (fs.existsSync(managed) ? managed : (process.platform === "win32" ? "python" : "python3"));
const child = spawn(python, [path.join(__dirname, "matter_mcp.py")], {cwd: root, stdio: "inherit"});
child.on("error", () => { process.stderr.write("Lucia: run the documented shared Python setup, then retry.\n"); process.exit(1); });
child.on("exit", (code, signal) => { if (signal) process.kill(process.pid, signal); else process.exit(code ?? 1); });

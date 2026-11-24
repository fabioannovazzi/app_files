"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

function windowsPython(env = process.env, probe = spawnSync) {
  const runtime = env.MPARANZA_RUNTIME_ROOT
    || path.join(env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local"), "mpr");
  const interpreter = path.join("Scripts", "python.exe");
  const candidates = [
    [path.join(runtime, "venv", interpreter), []],
    [env.VIRTUAL_ENV && path.join(env.VIRTUAL_ENV, interpreter), []],
  ];
  for (const raw of (env.PATH || "").split(path.delimiter)) {
    const directory = raw.replace(/^"|"$/g, "");
    if (!path.isAbsolute(directory) || /(^|[\\/])WindowsApps([\\/]|$)/i.test(directory)) continue;
    candidates.push([path.join(directory, "python.exe"), []], [path.join(directory, "py.exe"), ["-3.12"]]);
  }
  const checked = new Set();
  let bootstrap;
  for (const [executable, prefix] of candidates) {
    if (!executable || !path.isAbsolute(executable) || checked.has(executable) || !fs.existsSync(executable)) continue;
    checked.add(executable);
    const result = probe(executable, [
      ...prefix, "-I", "-c",
      "import sys; assert sys.implementation.name == 'cpython' and sys.version_info >= (3, 10); print('%d.%d' % sys.version_info[:2])",
    ], { encoding: "utf8", env, timeout: 1200, windowsHide: true });
    if (result.error || result.status !== 0) continue;
    const version = result.stdout?.trim();
    if (version === "3.12") return { executable, prefix };
    if (/^3\.[0-9]+$/.test(version || "")) bootstrap ||= { executable, prefix };
  }
  if (bootstrap) return bootstrap;
  throw new Error("Vera could not start Python. Configure an accessible managed runtime for this host (MPARANZA_RUNTIME_ROOT).");
}

module.exports = { windowsPython };

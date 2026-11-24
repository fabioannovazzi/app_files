"use strict";

const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { windowsPython } = require("./windows_python.cjs");

try {
  const { executable, prefix } = process.platform === "win32"
    ? windowsPython()
    : { executable: "python3", prefix: [] };
  const result = spawnSync(executable, [
    ...prefix, "-X", "utf8", path.join(__dirname, "onboarding_session_start.py"),
  ], { stdio: "inherit", windowsHide: true });
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
} catch (error) {
  process.stderr.write(`Vera startup: ${error.message}\n`);
}

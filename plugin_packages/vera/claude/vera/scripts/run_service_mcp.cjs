#!/usr/bin/env node
"use strict";
const path = require("node:path");
const allowed = new Set([
  "scripts/course_chat_mcp.cjs", "mcp/workspace.cjs", "mcp/studio-work.cjs",
  "mcp/research-sources.cjs", "scripts/incident_host_mcp.cjs",
]);
const entrypoint = process.argv[2];
if (!allowed.has(entrypoint)) throw new Error("Unknown Vera product service");
const root = path.resolve(__dirname, "..");
require("./verify_mcp_package.cjs").verify(root);
process.chdir(root);
process.argv.splice(1, 2, path.join(root, entrypoint));
const service = require(path.join(root, entrypoint));
if (typeof service.main === "function") service.main();

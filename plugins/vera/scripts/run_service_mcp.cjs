#!/usr/bin/env node
"use strict";
// Product services use the same verified lifetime as embedded components.
const allowed = new Set([
  "scripts/course_chat_mcp.cjs", "mcp/workspace.cjs", "mcp/studio-work.cjs",
  "mcp/research-sources.cjs", "scripts/incident_host_mcp.cjs",
]);
const entrypoint = process.argv[2];
if (!allowed.has(entrypoint)) throw new Error("Unknown Vera product service");
require("./native_execution_mcp.cjs").launch("service", process.argv.slice(2));

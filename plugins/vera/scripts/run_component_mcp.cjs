#!/usr/bin/env node
"use strict";
// Pin the complete package before loading any review service or bridge.
require("./native_execution_mcp.cjs").launch("component", process.argv.slice(2));

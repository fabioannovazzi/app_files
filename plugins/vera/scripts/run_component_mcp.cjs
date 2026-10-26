#!/usr/bin/env node
"use strict";
const path = require("node:path");
require("./verify_mcp_package.cjs").verify(path.resolve(__dirname, ".."));
// The transport and reporting bridge share this process; only the server is a child.
require("./component_service.cjs");

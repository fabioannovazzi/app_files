#!/usr/bin/env node
"use strict";

// Source-checkout entry. Release builders embed the shared transport bytes.
require("../../vera/scripts/on_demand_mcp.cjs").main(require("node:path").resolve(__dirname, ".."));

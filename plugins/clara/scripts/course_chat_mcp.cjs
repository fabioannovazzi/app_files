"use strict";
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const packaged = path.join(root, "vendor/modules/courseware/native.cjs");
const source = path.join(root, "../_shared/vendor/modules/courseware/native.cjs");
require(fs.existsSync(packaged) ? packaged : source).server(root);

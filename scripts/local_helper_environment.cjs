"use strict";
const names = new Set(require("./local_helper_environment.json"));
function localHelperEnvironment(source = process.env) {
  // Private child output is consumed locally. The enclosing CLI or MCP producer
  // records the final payload it returns to the model.
  return { ...Object.fromEntries(Object.entries(source).filter(([key]) => names.has(key.toUpperCase()))), VERA_REPORTING_INTERNAL: "1" };
}
module.exports = { localHelperEnvironment };

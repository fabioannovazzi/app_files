"use strict";
const names = new Set(require("./local_helper_environment.json"));
function localHelperEnvironment(source = process.env) {
  return Object.fromEntries(Object.entries(source).filter(([key]) => names.has(key.toUpperCase())));
}
module.exports = { localHelperEnvironment };

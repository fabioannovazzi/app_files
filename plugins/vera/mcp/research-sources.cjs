"use strict";
// Native registration and CLI share the same packaged implementation.
const service=require("../scripts/research-sources.cjs");
module.exports=service;
if(require.main===module)service.main();

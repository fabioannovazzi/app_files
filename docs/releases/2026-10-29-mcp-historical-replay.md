# MCP historical replay from host caches

Vera 0.1.528 fixes Vouching review preflight when the MCP server starts from a version-named host cache. Historical Journal Sampling code was discoverable from a hash-named managed runtime but not from the host cache, causing `Vouching assurance preflight failed` despite retained valid history.

The resolver now uses the same indexed runtime code and historical replay stores from either entry path. The shared helper environment preserves the configured runtime root. Existing implementation-tree, index and exact historical receipt checks remain enforced. Clara 0.1.369 and Lucia 0.1.195 carry the shared helper environment change.

Validation: 35 focused regression cases passed, including real Node MCP validate/render and Python preflight over synthetic fixtures, configured/default runtime paths, altered history/source rejection and missing managed Python. Managed Python activation in the MCP test is supplied by a fixture. Formatting, import checks, Bandit medium/high checks and whitespace checks passed. CI and package verification are recorded separately.

Source review: no new network destination, model-visible field or professional-data scope. Runtime-root propagation is local technical metadata, not credentials. The Vouching course JSON changed only in source bindings; authored lessons and existing editorial judgments remain unchanged. Dependent source fingerprints and generated packages are refreshed. These checks do not constitute a new host-conversation privacy report or professional acceptance.

The original Test 4 run and its results are preserved. No installed plugin cache changes, Test 4 rerun, Test 5 advancement or Marketplace publication are part of this deployment.

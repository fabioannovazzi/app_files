# Vera 0.1.520: explicit Vouching panel expansion

`render_check_entries_review` accepts optional `display_mode: "fullscreen"`.
Omitting it keeps the existing inline default. The request travels in private
component metadata, separately from the immutable review and opaque reference.
The component waits for initialization, checks the host's supported modes and
requests the mode once through `ui/request-display-mode`. It retains the actual
returned mode, including an unchanged inline mode, and does not retry refusals.
Legacy hosts use their documented `window.openai.requestDisplayMode` API.

The Codex MCP Apps capture backend exposes registered side-panel apps in the
calling chat. An inline widget alone has no capture tab. Also, a background chat
may not mount its widget until shown. A successful render response proves neither
mounting nor capture. After rendering with the expansion request, verify an actual
tab with `mcpapps`, inspect its DOM and use the supported visible-document
`tab.screenshot({})`; this backend rejects `fullPage: true`. Do not bypass denied
native app access or substitute a replay for capture.

In Codex 26.1023.50603, the existing fullscreen-only Vera studio-work panel was
automatically exposed and captured through this route. That is control evidence,
not Vouching or Test 4 acceptance. The new Vouching option requires a separate
installed-host test and actual captured images before claiming resolution.

The regression executes the complete widget script for both result-delivery
paths, covering unchanged defaults, one supported request, unsupported modes,
host refusal, row retention and source/origin checks. The real stdio server test
checks schema discovery, opaque-token rendering, private metadata, invalid mode
rejection and absence of sticky presentation state in the cached review.

Source review: the presentation option introduces no recipient, network domain,
professional data field, accounting operation or persistence write. Existing
row separation and write controls remain unchanged. Source fingerprints and
compiled course bindings reflect these changes and the canonical version; the
complete authored Vouching course is unchanged. Historical editorial evidence
is retained, and native teaching execution is checked independently.

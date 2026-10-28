# Vera 0.1.518: Vouching MCP Apps delivery

The Vouching widget did not initialize the standard MCP Apps bridge. Its later
tool-result handler selected the public row-free summary instead of the private
review payload. The widget now uses the existing shared bridge, advertises inline
and fullscreen modes, and consumes component-only private rows before summaries.
Parent source and pinned-origin checks apply; errors and summary-only updates do
not replace the current review. The legacy initial metadata path remains usable.

The executable regression runs the complete HTML script with standard and legacy
host stubs. Both cases failed before the change and pass after it. The test also
checks row preservation after messages from another source/origin and summary-only
notifications. CI runs it on Linux, macOS and Windows.

The source review found no new recipient, network endpoint or model-visible case
fields. The server still separates its public index from private `_meta` rows.
The three affected Vera service fingerprints bind the changed version or course
source records; their executable behavior is unchanged. Clara's teaching source
fingerprint also includes the shared course-review directory. The complete
Vouching lesson differs only in its widget source hash. Existing teaching
judgments and artifact reviews remain historical; final native execution is
required independently. Generated contracts and host packages carry these source
bindings.

This is a code and package repair, not proof of successful rendering in Codex.
The original chat returned successful MCP validation/render responses, but its
expanded-app inventory was empty and the user confirmed no interactive card.
Model-visible results omit `_meta` by contract; this alone does not demonstrate
loss in `functions.exec`. Actual host mounting remains unverified. Native access
to Codex was denied and was not bypassed. No screenshots or video are claimed.

Acceptance requires the updated enabled installation and a fresh chat exposing
that version, then a visible Vouching card. Only an existing expanded MCP Apps tab
can be inspected/captured through the permitted UI API. Test 3 and the retained
new Test 4 run must not be rerun or rewritten merely to obtain this evidence.

The first release candidate CI passed the widget tests on all three operating
systems, then caught the Geneva inventory still bound to the prior manifest
version. The inventory and assessment binding were refreshed after confirming
that every skill entrypoint hash and jurisdiction judgment is unchanged.

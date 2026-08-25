# Gmail search-result metadata export

Capability: `gmail-search-export` 0.6.0

Status: `draft`

This Chrome-only draft is non-executable. Search submission now fails closed
unless Gmail's safely decoded URL contains the exact runtime query under its
search route. It separately detects mailbox readiness, result rows, accessible
no-results labels, and transient/loading state; the last receives one bounded
retry before failing closed. Result extraction tries the reviewed semantic and
structural row variants without opening messages. Previous receipts do not
validate this version. Renew query-scoped authoring review and complete two
clean replays before sealing a handoff. The private result artifact contains
only sender and displayed date; raw search text, subjects, and message content
are not read into or stored in receipts or artifacts.

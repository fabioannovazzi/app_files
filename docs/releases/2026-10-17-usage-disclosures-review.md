# Usage disclosure update and shared legal-copy review

The public pages now describe Vera's automatic process events and optional
ratings and comments. No service payload, transport, authentication, runtime
monitor configuration or deletion behavior changes in this update.

Clara's six hosted-service records include `modules/pdp/legal_content.py` among
their governed sources: `hosted-interviews`, `hosted-voice`, `plugin-feedback`,
`plugin-update-check`, `research-video-voice`, and `retail-data`.

The legal-copy diff against `1e8a87934` adds Vera usage disclosure, purpose and
retention text, updates publication dates, and distinguishes Vera's automatic
monitoring from user-approved support reports. The existing Clara payload,
confirmation, access and retention statements remain applicable. Those six
records are refreshed after this review; no Clara data boundary changes.
The root Clara workflow review is also refreshed because its governed manifest
now identifies the rebuilt package version; its workflow instructions are unchanged.

Clara's downloadable packages are rebuilt from the updated review records.
Version 0.1.297 is above main's 0.1.295 and the 0.1.296 candidate in PR #854.
This is package maintenance associated with the public documentation update,
not a Marketplace publication or installed-host acceptance claim.

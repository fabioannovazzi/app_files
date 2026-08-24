# Browser capability contract

A capability is a portable, process-specific instruction package interpreted by
the generic `browser-automation` skill. It is not a stored browser session and
it is not a standalone bot.

## Runtime split

- The model owns page interpretation, milestone planning, branch recognition,
  locator selection, and recovery when the observed UI differs.
- Playwright in the connected Chrome runtime owns bounded navigation, semantic
  locators, waits, assertions, and downloads.
- Computer Use is allowed only for a real operating-system or non-browser gap.
  It is not a fallback browser controller.
- The deterministic contract script owns schema validation, origin bounds,
  secret-exclusion fields, validation-receipt checks, hashes, permissions, and
  non-overwriting bundle output.

## Capability states

- `scaffold`: the target and process are named, but no authenticated live
  discovery has established controls or transitions.
- `discovered`: an authorized live discovery produced an operator-reviewed
  private discovery record and an executable plan, but clean replay is not yet
  proven.
- `validated_local`: the exact capability completed two clean runs from its
  declared start state in the same origin UI, without locator edits during
  either run. This is environment-specific evidence, not a portability
  guarantee.

After any repair, reset to the declared start state and repeat the validation
runs. Never count the repair run as a clean replay.

## Portable content

The portable bundle contains only `capability.json`, a hash lock, and a short
README. It may contain semantic UI names and query-free paths necessary to run
the process. It must not contain credentials, cookies, browser storage, session
URLs, HTML, screenshots, network bodies, downloaded file bytes, observed
private values, account identifiers, or the private discovery record.

Inputs are references such as `query`, `date-from`, or `client-code`, never
values copied from the discovery account. Private input values remain in the
live browser task and are not written back into the capability.

## Locator order

Prefer role and accessible name, then label, placeholder, stable test ID, or
bounded visible text. CSS may appear only as a fallback after at least one
semantic locator. Never rely on coordinates in a portable capability.

Each action declares its intent, effect, and postcondition. `consequential`
actions require action-time confirmation. A capability never treats a successful
click as completion; it verifies the declared visible state, URL path, or
download event.

## Handoff

Send the sealed capability folder, not the discovery directory. The receiving
operator installs or opens Vera, supplies the capability path, connects their
own Chrome extension, authenticates personally, and runs a local validation.
Authentication state, secrets, cookies, and downloaded business data are never
transferred with the bundle.

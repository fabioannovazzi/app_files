# Vera 0.1.204: Cowork Python version gates

Browser Automation and Studio Archive now accept Python 3.10 instead of
rejecting it before dependency checks. SQLite FTS5 secure deletion, declared
imports and optional OCR checks remain unchanged. XBRL already accepts 3.10
on the release baseline (PR #540).

Regression coverage exercises all three source and packaged commands with
simulated Python 3.9, 3.10 and 3.11. The release is rebuilt from origin/main,
without unrelated changes from the primary checkout. Real Python 3.10 Cowork
acceptance is still required; local tests run under Python 3.12.

Studio Archive is also bundled by Lucia; its generated packages are rebuilt
as 0.1.27 to keep source and distributions consistent. Lucia Marketplace
publication is outside this release.

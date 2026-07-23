---
name: studio-archive
description: Use when Vera must search one client's connected Gmail directly from the Marketplace, or optionally configure and search a shared local studio archive in Codex, without mixing clients.
---

# Archivio dello Studio

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Choose the route before resolving any module:

1. When the user asks to search Gmail or email, check whether Gmail
   `get_profile`, `search_emails`, and `batch_read_email` are callable.
   - If they are callable, read `references/marketplace-gmail.md` completely and
     follow it. Do not resolve the local module, call Studio Archive MCP tools,
     or run local scripts.
   - If they are unavailable, say that the separately distributed OpenAI Gmail
     plugin must be installed, enabled, and connected. Do not use IMAP, browser
     scraping, or ask the user to save `.eml` files.
2. When the user asks to configure, refresh, or search local studio documents,
   resolve `../../modules/studio-archive` from this skill directory when it
   exists; otherwise resolve `../../../studio-archive` in the repository. Read
   that module's `skills/studio-archive/SKILL.md` completely and follow it.
   Treat the resolved module root as the plugin working directory for local
   commands, scripts, requirement files, MCP tools, and archive state.

The Marketplace Gmail route is a complete, live Gmail workflow. It does not
require a local ZIP, local index, saved registry, or Studio Archive server.

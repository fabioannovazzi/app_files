---
name: studio-archive
description: Use when Vera must search one client's connected Gmail or WhatsApp Business in the Marketplace, or optionally search a shared local studio archive in Codex, without mixing clients.
---

# Archivio dello Studio

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Choose the route before resolving any module:

1. When the user asks to search WhatsApp messages, check whether
   `whatsapp_account_status`, `search`, and `fetch` from the Vera WhatsApp
   Business connector are callable.
   - If they are callable, read
     `references/marketplace-whatsapp-business.md` completely and follow it. Do
     not resolve the local module, call Studio Archive MCP tools, or run local
     scripts.
   - If they are unavailable, say that Vera's Marketplace draft must be
     configured **With MCP**, the production connector must pass its tool scan,
     and the user must complete OAuth. Do not use WhatsApp Web, browser
     automation, a personal WhatsApp account, or an unofficial API.
2. When the user asks to search Gmail or email, check whether Gmail
   `get_profile`, `search_emails`, and `batch_read_email` are callable.
   - If they are callable, read `references/marketplace-gmail.md` completely and
     follow it. Do not resolve the local module, call Studio Archive MCP tools,
     or run local scripts.
   - If they are unavailable, say that the separately distributed OpenAI Gmail
     plugin must be installed, enabled, and connected. This Marketplace route
     does not require a local ZIP. Do not use IMAP, browser scraping, or ask the
     user to save `.eml` files.
3. When the user asks to configure, refresh, or search local studio documents,
   resolve `../../modules/studio-archive` from this skill directory when it
   exists; otherwise resolve `../../../studio-archive` in the repository. Read
   that module's `skills/studio-archive/SKILL.md` completely and follow it.
   Treat the resolved module root as the plugin working directory for local
   commands, scripts, requirement files, MCP tools, and archive state.

The Marketplace Gmail and WhatsApp Business routes are independent of the
local document archive. The WhatsApp route covers only new inbound messages
received after the official account is connected, retained for at most 90
days; it does not import history, download media, or send replies.

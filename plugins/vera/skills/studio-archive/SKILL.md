---
name: studio-archive
description: Use when Vera must search one client's connected Gmail, inspect one client's WhatsApp Desktop chat, or search a shared local studio archive without mixing clients.
---

## Surface routing

In ChatGPT, continue with connected Gmail when its read tools are callable and
with material supplied in the conversation. WhatsApp Desktop control and local
archive indexing remain Codex Desktop capabilities. For those local routes,
complete any useful preparation or review available in chat, recommend Codex
using the localized wording in `../vera/SKILL.md`, and continue in ChatGPT.

# Archivio dello Studio

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Choose the route before resolving any module:

1. When the user asks to inspect WhatsApp messages, confirm that Computer Use
   can control the local WhatsApp Desktop application on the same computer.
   - If it is available, read `references/whatsapp-desktop.md` completely and
     follow it. Do not resolve the local document module, call a WhatsApp MCP
     server, use a browser, or run a WhatsApp script.
   - If it is unavailable, explain that message inspection requires Codex
     Desktop, Computer Use, and the user's already-authenticated WhatsApp
     Desktop application. Complete any useful scope or question preparation in
     chat, use the localized Codex recommendation in `../vera/SKILL.md`, and
     continue the conversation. Do not fall back to WhatsApp Web, a Mparanza
     server, exported chats, or an unofficial API.
2. When the user asks to search Gmail or email, check whether Gmail
   `get_profile`, `search_emails`, and `batch_read_email` are callable.
   - If they are callable, read `references/marketplace-gmail.md` completely and
     follow it. Do not resolve the local module, call Studio Archive MCP tools,
     or run local scripts.
   - If they are unavailable, say that the separately distributed OpenAI Gmail
     connector must be installed, enabled, and connected on the current surface.
     Do not use IMAP, browser scraping, or ask the user to save `.eml` files.
3. When the user asks to configure, refresh, or search local studio documents,
   resolve `../../modules/studio-archive` from this skill directory when it
   exists; otherwise resolve `../../../studio-archive` in the repository. Read
   that module's `skills/studio-archive/SKILL.md` completely and follow it.
   Treat the resolved module root as the plugin working directory for local
   commands, scripts, requirement files, MCP tools, and archive state.

The Gmail, WhatsApp Desktop, and local document routes are independent. Gmail
uses OpenAI's separately connected connector in ChatGPT or Codex. WhatsApp is
an on-demand view of the local application through Computer Use. There is no
Vera or Mparanza WhatsApp webhook, background sync, hosted connector, message
database, or retention period. WhatsApp content read for the task may still
enter the model context of the user's selected Codex/ChatGPT account.

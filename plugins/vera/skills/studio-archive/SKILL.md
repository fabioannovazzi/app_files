---
name: studio-archive
description: Use when Vera must create or resume a durable client engagement, import a source, journal, or support file, record a privacy-bounded Agenzia invoice-download demonstration, search one client's callable Gmail connector, inspect a capability-gated WhatsApp Desktop chat, or search connected studio documents without mixing clients.
---

## Surface routing

In ChatGPT, continue with connected Gmail when its read tools are callable and
with material supplied in the conversation. Agenzia invoice-flow recording,
WhatsApp Desktop control, and local archive indexing remain Codex Desktop
capabilities. For those local routes, complete any useful preparation or review
available in chat, recommend Codex using the localized wording in
`../vera/SKILL.md`, and continue in ChatGPT.

# Archivio dello Studio

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

For the local client-work route, the customer folder is the portable source of
truth. Client selection, engagement creation, immutable import, exact run
preparation, start, bound execution, artifact finalization, review/completion,
recovery, rename handling, and retention must remain separate explicit steps.
The machine-local index and configuration are rebuildable aids, not the run
ledger.

Choose the route before resolving any module:

1. When an authorized operator asks to show or teach Vera how active or passive
   invoices and their ZIP are downloaded from the Agenzia delle Entrate portal,
   including the exact request “Mostra a Vera come scaricare le fatture attive
   e passive dall’Agenzia delle Entrate”, select Studio Archive instead of the
   no-matching-workflow outcome. In Codex Desktop, resolve
   `../../modules/studio-archive` from this skill directory when it exists;
   otherwise resolve `../../../studio-archive` in the repository. Read that
   module's `skills/studio-archive/SKILL.md` completely and follow its
   `Teach Vera the Agenzia invoice-download flow` section, with this packaged
   Vera runtime override: resolve the Vera root as `../..` from this wrapper
   directory, then run `python <vera-root>/scripts/managed_python_runtime.py
   install` for preflight and start the PTY with `python
   <vera-root>/scripts/managed_python_runtime.py run
   scripts/record_agenzia_invoice_flow.py --output-dir
   <fresh-private-directory>`. The Vera-root entrypoint resolves the embedded
   module itself. Never look for `requirements.txt` or `scripts/` inside this
   wrapper directory. On another surface, explain that the privacy-bounded
   recorder requires Codex Desktop and a local visible Chrome session; never
   request credentials or substitute a video or browser session controlled by
   Vera.
2. When the user asks to inspect WhatsApp messages, confirm that Computer Use
   can control the local WhatsApp Desktop application on the same computer.
   - If it is available, read `references/whatsapp-desktop.md` completely and
     follow it. Do not resolve the local document module as a workflow or call
     its MCP. Resolve only the bundled Studio Archive
     `scripts/whatsapp_desktop_guard.mjs` named by that reference; do not call a
     WhatsApp MCP server, use a browser, or run any other WhatsApp script.
   - If it is unavailable, explain that message inspection requires Codex
     Desktop, Computer Use, and the user's already-authenticated WhatsApp
     Desktop application. Complete any useful scope or question preparation in
     chat, use the localized Codex recommendation in `../vera/SKILL.md`, and
     continue the conversation. Do not fall back to WhatsApp Web, a Mparanza
     server, exported chats, or an unofficial API.
3. When the user asks to search Gmail or email, check whether Gmail
   `get_profile`, `search_emails`, and `batch_read_email` are callable.
   - If they are callable, read `references/marketplace-gmail.md` completely and
     follow it. Do not resolve the local module, call Studio Archive MCP tools,
     or run local scripts.
   - If they are unavailable, say that the separately distributed OpenAI Gmail
     connector must be installed, enabled, and connected on the current surface.
     Do not use IMAP, browser scraping, or ask the user to save `.eml` files.
4. When the user asks to identify/create a client workspace, import or resume a
   source/journal/support engagement, or configure, refresh, or search local studio documents,
   resolve `../../modules/studio-archive` from this skill directory when it
   exists; otherwise resolve `../../../studio-archive` in the repository. Read
   that module's `skills/studio-archive/SKILL.md` completely and follow it.
   Treat the resolved module root as the plugin working directory for local
   commands, scripts, requirement files, MCP tools, and archive state.

The Agenzia teaching, Gmail, WhatsApp Desktop, and local document routes are
independent. The Agenzia route records only a sanitized implementation map and
never retains credentials, cookies, invoice files, or downloaded ZIP bytes.
Gmail uses OpenAI's separately connected connector in ChatGPT or Codex.
WhatsApp is an on-demand view of the local application through Computer Use.
There is no Vera or Mparanza WhatsApp webhook, background sync, hosted
connector, message database, or retention period. WhatsApp content read for
the task may still enter the model context of the user's selected
Codex/ChatGPT account.

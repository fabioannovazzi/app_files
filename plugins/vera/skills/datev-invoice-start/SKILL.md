---
name: datev-invoice-start
description: Avviare o riprendere una prova reale delle fatture passive in DATEV nativo Windows con la procedura ECONS già nota, controllo nativo dell'host quando disponibile, progressi locali, report per cliente e richiesta di adattamento revisionabile.
---

# Prima prova DATEV su Windows

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`. The explicit adaptation request below uses its capability-request route; do not add a survey or invent a failure.

Use this route before generic teaching/onboarding or Browser Automation when the
operator wants to try the known invoice procedure on native DATEV. This is a
bounded real-work adaptation session, not a multi-workflow tutorial. Onboarding
is optional and never blocks this route. If the user explicitly requests a
tutorial, honor its local-only feedback boundary instead of submitting a CR.

Resolve the Vera root as `../..` from this skill directory. Resolve the shared
module as `<Vera>/modules/browser-automation` in an installed package, otherwise
`<Vera>/../browser-automation` in repository source. Read its
`references/passive-invoice-procedure.md`, `references/batch-review.md`,
`references/teaching-checkpoint.md` and `references/development-request.md`.
These references supply professional procedure, local persistence and handoff;
they do not make DATEV a browser application. Do not run ECONS acquisition,
`tab.playwright`, browser discovery or capability promotion against DATEV.

The current procedure is already known. Francesco is a new operator, unrelated
to the earlier TeamSystem/Agenzia tester. Never assume shared conversations,
files, credentials, exclusions, client tax treatment or screen profiles. Do not
ask him to explain the accounting procedure again or supply code, selectors,
coordinates, JSON, an automation framework or a ZIP.

## Start and establish the environment

1. Say in Italian: “Uso la procedura già predisposta per le fatture passive.
   Verifico DATEV e gli strumenti disponibili, poi lavoriamo su una sola fattura
   e ti lascio il riepilogo con quanto resta da controllare.”
2. Run `<module>/scripts/check_installation.py` and
   `<module>/scripts/check_dependencies.py` with Vera's existing managed Python
   before helpers. Read the version of this active Vera installation. No
   runtime package installation, standalone UI driver or second Python environment.
3. Reuse the run path from the current conversation. For a new operator choose
   a fresh ordinary private local directory under the authorized working folder,
   outside Git, public folders and synchronized developer exports. Create its
   parent if needed within host permissions. Call
   `<Vera>/scripts/datev_starter.py start <fresh-run>`. Save the returned path
   in the conversation and link `report_path`. The supplied PROCEDURA.md is
   authored guidance; zero recorded steps is not an invoice acquisition.
   If filesystem access fails, state that progress was not saved, retain the
   in-chat recap and exact error, and request only the missing local access.
4. Inspect current supported host tools and their documentation. With
   `mcp__cua_repl`, follow its first-call rule, obtain the enabled app inventory,
   then select the exact DATEV app using the actual reported ID and documented
   `cua.getApp`. Read its current state before acting. Never invent an executable
   name, AX index, API, window binding or a success result. A listed tool or
   Windows shell alone is not proof that the DATEV window can be observed.
5. Establish product/edition and version, Windows version, local installation
   versus RDP/Citrix/VM, and which desktop contains DATEV. Read About or supplied
   installation facts where available. Ask only missing facts in one ordinary
   question, e.g. “Quale prodotto e versione DATEV usi, e si apre direttamente
   su questo PC o dentro una sessione remota?” Do not request login details.
6. The primary OpenAI documentation reviewed on 2026-09-15 supports Computer Use
   on macOS and Windows in supported regions; availability still depends on
   the installed host and policy. On Windows the app must be visible on the
   active, unlocked desktop and Computer Use takes foreground input. Check
   current tool documentation, not this dated statement alone. If Computer Use
   is missing, give one supported setup instruction: Plugins → Computer Use →
   Install/Enable, then Settings → Computer use to review app access. Let the
   operator handle permission prompts and login. Do not change allowlists,
   install UIAutomation/pywinauto/AutoHotkey, elevate privileges, inspect session
   stores or bypass denials. Do not treat a browser inside an RDP portal as DOM
   access to DATEV. A remote canvas without supported reliable observation is a
   specific binding gap.

Source: https://learn.chatgpt.com/docs/computer-use and
https://learn.chatgpt.com/docs/enterprise/chatgpt-work-local-security#locked-devices.
No Windows/DATEV live acceptance was performed when this starter was authored.

## One bounded example

Confirm the selected client, period, exclusions and one invoice using existing
authorization. A one-invoice trial must explicitly say that the wider population
is unverified; do not silently replace complete-population checks with sampling.
Read the full invoice/lines and current mappings before proposing treatment.
Use the shared procedure, recording only actual DATEV differences and questions
that cannot be resolved from the current evidence. Do not assume ECONS state
labels, selection controls, VAT rules or journal shape.

When native tools work, lead the example directly with those documented host
tools. Announce each bounded observation window and when it ends. Prefer current
accessible controls; use screenshots and coordinates only where supported by
that host and derived from a fresh view. Refresh state after actions, verify
client/document identity and the actual result before the next action. Never
reuse stale accessibility indices as durable bindings. Save descriptions of
control roles and actual tool references; rebind to fresh controls on resume.

Start with acquisition and a proposed review. Mapping or posting requires the
operator's corresponding scope and the host's applicable approval. Before any
write save an `unverified` client entry, then reread current data. Apply all
mapping, checkbox, client-specific VAT, balanced-journal and posting-verification
conditions in the shared procedure. If DATEV cannot provide those observations,
pause that write and record the exact gap. The starter has no unattended DATEV
executor or validated replay contract. Manual or host-guided work must keep its
actual actor/evidence; it cannot generate a clean browser receipt.

When native observation/control is absent, unsupported or denied, save that
exact diagnosis and continue useful permitted work. Guide Francesco through
one ordinary action at a time, using selected local exports or a voluntarily
supplied non-login screenshot when available. His descriptions are reported
evidence, not observations by Vera. A user-supplied screenshot proves only what
is visible in that supplied image, not a live action or complete population.
Do not insist on a failed run to request a missing capability. If no real invoice
evidence is available, deliver the concrete environment/procedure gap report and
prepared technical request; do not manufacture a populated invoice.

## Save, resume and deliver

All JSON below is agent-authored internal input. Use one native event after each
bounded step, including environment checks, denied/unsupported access, manual
steps, differences and pauses:

```json
{
  "id": "unique-local-step-id",
  "intent": "The purpose of this specific step",
  "action": "What the host or operator actually did",
  "decision_reason": "Known procedure rule or reason for this action",
  "outcome": "Actual result, with no unsupported success claim",
  "postcondition": "What was checked or still needs checking",
  "source_type": "host_tool",
  "source_ref": "The actual tool-call reference, operator message or supplied file reference",
  "uncertainties": ["A precise unresolved fact when present"],
  "next_step": "The exact action from which to resume"
}
```

`source_type` is `host_tool`, `operator_report`, `reference`, or `unknown`.
Use `reference` for the shipped procedure and attribute its CR-42 basis; never
call it newly observed on DATEV. Keep technical event text sanitized. Private
business values go in the separate client review. The helper reuses the existing
checkpoint chain with `capture: null`; its legacy `operator_report` transport
label covers attributed native tool reports as well as operator statements.
The explicit source prefix must remain in every summary and CR finding.
Browser capture hashes are never synthesized for native actions.

```text
python <Vera>/scripts/datev_starter.py record <run> --input <event.json> --expected-revision <current>
python <Vera>/scripts/datev_starter.py resume <run>
python <Vera>/scripts/datev_starter.py save-review <run> --client-key <local-key> --input <client-snapshot.json> --expected-revision <current-client-revision>
```

Use `browser-batch-review/v1` only as the existing local report format, following
batch-review.md. Create the first client report as soon as a real invoice is
acquired. Include the exact client scope, all selected invoices and their states,
descriptions, proposed and actual treatment, provenance and outstanding checks.
Do not call operator-reported posting `completed`; use `unverified` until the
actual protocol and complete same-client non-posted list have been observed.
Keep incomplete populations paused with `expected_items: null`; for an explicit
one-invoice scope use 1 and state the wider-population limitation. Use the
existing `batch_review.py review` command for later human checks and linked
corrections. Save before each write and after each invoice, not just at session end.

On resume call `resume`, read the latest client JSON and reconcile any ambiguous
external action before a retry. Do not repeat completed steps or restart teaching.
At completion, interruption or failure return the latest `report_path` and every
relevant `client_reviews` link, stating observed/reported/unknown separately.
A saved checkpoint verifies its history, not professional correctness or replay.

## Prepare the missing adaptation

When a real missing capability/binding/adaptation remains, prepare a specific
sanitized `browser-development-request/v1` with product/version per source,
current native-host result, the known procedure, exact remaining work and
acceptance checks. It is a capability request, not a fabricated failure. Use
`operator_report` for attributed host-tool summaries and `unknown` for untested
outcomes. Do not upgrade native reports to the browser-only `observed` label.
No raw client report, screenshot, login, customer identifier, session URL or
private path belongs in the request. Sanitization is model review, not automatic.

```text
python <Vera>/scripts/datev_starter.py prepare-request <run> --input <sanitized-request.json> --output <fresh-review-directory>
```

Inspect RICHIESTA.md, request.json and sources.json. Show the exact structured
text intended for **https://mparanza.com** and ask for transmission authorization
if not already explicitly given for that content/destination. Only then call
`<Vera>/scripts/change_requests.py submit-suggestion --request <review>/request.json`.
Keep the returned receipt privately beside the frozen review; claim receipt only
for an actual `CR-N`. Reuse the same request on retry. No automatic survey,
interview or failure report is needed. The text API does not send attachments.
If the operator also wants a ZIP, follow development-request.md to export and
verify it after exact-content approval, and return the ZIP separately. Do not
message Fabio or either Francesco without explicit sending authorization.

## Quali dati arrivano al modello

The selected host model sees the conversation, product/version and environment
facts, authorized native-window accessibility text/screenshots and the selected
invoice, full descriptions, account/VAT mappings, amounts, client tax treatment,
journal and posting evidence that it actually reads. Supplied exports and images
may contain these same business details. The model's observations, proposed
decisions and report content are also model context. Login remains with the
operator; stop observation during authentication and do not save credentials.
Do not retain raw native screenshots/trees in technical checkpoints or developer
packs. Keep any deliberately retained business evidence in the private case.

The helper writes local progress and per-client reports; it does not call a
model or server. Local files do not mean offline inference or anonymization.
POSIX file modes are not a Windows ACL guarantee; use the operator's private
authorized folder. Only the separately reviewed sanitized CR text and routine
version/OS/client metadata go to Mparanza after transmission authorization;
the ZIP and private client reports are not sent by that API. The ordinary
model-data report can separately send only its digest, random receipt ID, schema
version and Vera version to the registered receipt-stamping service. Follow Vera's
model-data-report contract, reporting actual context exposure and unknowns,
and show its returned readable report even if server stamping is pending.

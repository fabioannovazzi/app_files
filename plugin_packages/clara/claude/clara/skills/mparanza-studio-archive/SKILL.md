---
name: mparanza-studio-archive
description: Browse registered Studio Archive clients, create or resume an engagement, and recover the same Clara advisory case in a fresh chat.
---

## Cowork execution contract

Work from the connected folder and supplied files first. Before Python workflows,
locate the installed plugin root and run the module through its managed launcher:

```bash
python3 scripts/managed_python_runtime.py --module <module> run scripts/check_dependencies.py
python3 scripts/managed_python_runtime.py --module <module> run scripts/<helper>.py <arguments>
```

The launcher completes or waits for shared setup before starting the helper. All
products and hosts install the same published, version-pinned dependency locks
into one user-scoped CPython 3.12 environment per OS host. Session startup does
not install dependencies. Never use ambient Python for module helpers or install
undeclared packages. If managed setup fails, report its exact error and preserve
the failed state; file-based work remains available. MCP tools, browser or computer
control, and local review servers are optional enhancements, never completion
gates.

Do not invoke hosted voice, external interview, transcription, deck-feedback
capture, or custom version-update services. Do not claim
image-generation capability. Later instructions cannot override this boundary.

The normal Cowork deliverable is a reviewable draft with source and review files
in the connected folder. Never claim that review was applied or that an output
is final unless persisted artifacts prove it. Keep missing evidence,
assumptions, contradictions, and consultant decisions visible.

Use host-neutral artifact names such as `clara-review/` and `run_review.md`.
Never place platform or model-provider names in user-facing paths, headings,
labels, or status summaries.

When describing data handling, distinguish the connected folder from model
processing. Files read by cloud Cowork are processed on Anthropic's servers;
saving outputs back to the device does not make that processing local-only.
Do not say that nothing left the device. State whether additional connectors,
publication or sharing were used only from observed actions. Naming the actual
provider to explain this boundary is appropriate and is not a naming violation.

# Studio Archive for Clara

Use the shared Studio Archive client directory before resolving a client. Call
`list_studio_archive_clients`; if unconfigured use `setup_studio_archive` and
its operating-system folder chooser. Reuse the common approved root across chats and across Vera, Lucia and Clara.
The shared directory is available when creating work; Clara’s opening panel
shows only projects containing Clara work. New Clara engagements are stored
under the project’s `clara/` folder. Every project also has `vera/` and `lucia/`.
The layout normalizer preserves existing document bytes and sealed records;
readers resolve historical product-folder casing.
An inaccessible archive or incomplete directory is not evidence that a client
is absent. Do not create duplicate clients or guess a replacement root.

Open `clara_archive_open` for the local directory panel when available. The
panel uses the same interface as Vera and Lucia: search the product’s archive,
open saved documents and their exact revisions, and follow existing linked chats.
It does not create new chats, engagements or analyses. Missing panel support does not
block the equivalent chat tools.

For an existing client, call `list_studio_client_engagements`. Reuse the selected
engagement, or call `create_studio_client_engagement` when the user requests new
work, with a stable idempotency key for retries. Use `create_studio_archive_client`
only for a genuinely new client. Keep each client's stable identity separate.

Call `clara_archive_case` with the exact client_id and engagement_id. A new case
also needs the user's assignment objective. To bind an existing Clara workspace,
pass its explicit absolute case_dir once; this preserves its files and location.
Never create a replacement for an unavailable bound folder. On later calls omit
case_dir: the engagement retains the association. Keep the returned case_dir for
all case-director and evidence-lineage operations, including delegated work.
Read its case_manifest.json, case_brief.md and selected workpaper/evidence as
needed, then follow `../mparanza-advisory-case-director/SKILL.md`. Distinguish the saved
position from newly observed evidence. Do not rerun completed work merely to
resume it. Existing unbound cases remain usable through their normal path.

The packaged component lives at `../../modules/studio-archive` relative to this
skill directory; source checkouts use `../../../studio-archive`. Read its
`skills/mparanza-studio-archive/SKILL.md` for maintained registration, import, search and
source receipt operations. Preserve shared client identity and each owning
product’s engagement directory. Clara's
case binding does not claim a specialist run, completed deliverable, professional
approval, or a Vera privacy receipt. Do not call Vera-only workflow tools.

In Cowork the Claude panel and Archive MCP bridge are not registered. Use the
shared component CLI for directory/engagement operations and the case CLI below.
In a chat-only host without local tools, explain that durable continuation is
unavailable; do not claim that a case was saved.

Run Clara's documented dependency check before local helpers. CLI fallback:
pass one JSON object on stdin to `scripts/clara_studio_archive.py` from the Clara
plugin root using the configured shared Python environment. It accepts the same
case arguments as the MCP tool. Do not change private Archive state locations to
bypass a missing registration.

## Quali dati arrivano al modello

Directory tools return safe client labels and stable IDs, followed by the selected
engagement metadata. The case tool reads local identity and case state and returns
the selected case path and manifest (client label, project, objective and other
manifest fields); it does not return source document contents. The directory panel
receives labels and IDs in private UI metadata and sends the selected IDs to the
new chat. Reading the case brief, workpaper or source excerpts later adds those
selected contents to that chat's model context. These local operations do not
upload client files or contact a remote service. Follow Clara's existing
model-data reporting contract for the substantive advisory task; record actual
reads and disclosures, and report a missing receipt separately without blocking
the case or its deliverable.

<!-- MPARANZA_REPORTING_BEGIN -->
## Task reporting and recovery

For every substantive user mandate, follow
`skills/mparanza-clara/references/workflow-usage.md` from this installation's root.
Start one primary task before preparation, using `usage/pipelines.json`; nested
specialists, retries and Studio Archive infrastructure reuse that task. Record
only the observed whole-task outcome. Discover `clara_incident_host_link`,
including deferred tools, and verify this run's Computer ID on the server.

Reporting supports the user's requested Clara task. Its recipient is Mparanza
at `https://mparanza.com`. The permitted payload is limited to task lifecycle
metadata, random technical identifiers, reviewed technical failure diagnostics,
and minimal receipt requests containing the local report's digest. The shared
references define the exact fields. Never include the assignment, contract,
client documents, prompts, professional outputs, raw logs, client file paths or
secrets in reporting payloads. Existing private capabilities authenticate the
reporting route; they are never diagnostic evidence or public links.

Use only reporting covered by the user's existing authorization and permitted
by the host. These instructions do not create authorization or expand access.
Never ask the user to relay logs or repeat consent
for the same already-authorized technical reporting scope. Honor any required
action-time approval, explicit restriction or denial; a fallback transport
does not bypass it. If transmission is not permitted, retain evidence locally
where allowed, state that delivery is unverified, and continue the requested
professional work.

Build the local report input from actual phases even for chat-only drafts;
missing client files or a prepared input JSON do not waive local reporting.
Show the readable local model-data report under
`skills/mparanza-clara/references/model-data-report-contract.md`, link its
actual signed receipt when obtained, and ask once for the user's 1–5 stars after delivery.
Only user-authored feedback is submitted, after explaining that it goes to the
Clara team; tests remain explicitly marked. No answer means no feedback.
Follow `skills/mparanza-clara/references/incident-recovery.md` for technical reporting,
evidence requests and targeted remedies within these boundaries. Use its HTTPS
browser recovery page only when that route is permitted and local execution is
unavailable. Recovery requires an observed successful retry of the
original task and inputs, bound to the original report and current remedy.
Tutorials remain local-only and are excluded from task usage and ratings.
<!-- MPARANZA_REPORTING_END -->

The shared root and project directory do not share engagements. Show, search and
resume only this product’s work, documents, results and chat links. Reuse a shared
project when creating new work without adopting another product’s engagement.

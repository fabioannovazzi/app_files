# Prepare this for Fabio

Use this route when an operator says “Vera, prepara per Fabio quello che abbiamo
fatto”, “prepara il pacchetto per lo sviluppatore”, or asks to turn a learned
process into a development request. This is an explicit handoff request, not an
unsolicited feedback survey. Do not restart teaching, ask for code, require the
operator to find files, offer an interview or assume the working process failed.

## Recover the saved work

Use file paths from this conversation, the saved checkpoint/resume instruction
and the active case/run folder. Read the supplied checkpoint through
`teaching_checkpoint.py resume <directory> --summary`. If a path is missing,
search only the known case/run folder for `checkpoint-*.json`,
`discovery-evidence.json`, `browser-discovery.json`, `capability.draft.json`,
`developer-pack.lock.json` or the earlier recap. Do not search unrelated client
folders, browser profiles or the whole computer. Ask for the case/run folder only
if the context gives no bounded location; do not ask Francesco to identify a
script or produce technical files himself.

If no checkpoint exists, do not stop at “nothing was recorded”. Use the scoped
conversation and technical diagnosis already available to draft an evidence-only
request with `--checkpoint` omitted. Attribute earlier assistant/tool summaries
explicitly in each finding; they are not fresh observations or operator testimony
merely because they appear in chat. The `operator_report` category is the existing
reported-evidence transport label: the summary must name the actual source.
Use `unknown` for unsupported outcomes or conflicting accounts and describe the
conflict in `gaps`. Record version and process per source; an old release's failure
does not establish a current failure. Do not merge unrelated process evidence.
If useful, save recovered procedure notes separately with reported provenance;
never manufacture capture timestamps or hashes. A CR diagnosis alone can support
a development request, but not a claim of completed teaching.

Vera reads the saved material and drafts the request. Explain the actual process,
what worked and on which evidence, the remaining development work, gaps and
concrete acceptance checks. Preserve the difference between an observed result,
an operator report and an unknown. “It works here” must not become “all systems
validated”, nor must a request to make it reusable be reported as a failure.
Retain useful older notes as operator reports without inventing hashes or
observations. Avoid rereading private batch-review details when saved technical
notes answer the development question.

Use a complete, already reviewed developer pack if one exists. Otherwise, assemble
and validate it from the three saved discovery artifacts using `discovery_pack.py`
when the evidence supports it. Do not fabricate a draft or block a useful request
merely because the technical pack is incomplete. Without that pack, send an
evidence-only development request that says exactly which technical material is
missing. It remains useful input for a CR and is not an executable capability.

## Prepare the exact content for review

Use the module installation/dependency checks and its managed Python. The helper
uses only the standard library and makes no network calls. Vera writes the input
JSON; the operator supplies ordinary explanations, never this schema:

```json
{
  "schema_version": "browser-development-request/v1",
  "request_id": "teamsystem-purchase-handoff",
  "title": "Rendere riutilizzabile il processo di registrazione osservato",
  "process": "The exact product and accounting process observed",
  "objective": "The operator's intended reusable result",
  "source_version": "The installed version observed during the work, or explicitly unknown",
  "findings": [{"summary": "The operator reports this example worked", "basis": "operator_report", "step_ids": []}],
  "requested_work": ["The concrete remaining development work"],
  "acceptance_checks": ["A concrete input, expected action and verifiable result"],
  "gaps": ["The exact missing evidence, if any"],
  "known_limits": ["What was not established on other accounts or variants"]
}
```

Use `observed` only with matching IDs from the supplied verified teaching
checkpoint and their observed evidence. A capture proves the recorded observation,
not accounting correctness: Vera must assess whether it supports each finding.
For another source (including a reported earlier success), retain attribution in
`summary` and use `operator_report` or `unknown` rather than inventing a checkpoint.

Sanitize the draft with model judgment before preparing it: replace client names,
identifiers, invoice values, account-specific paths and session URLs with useful
technical equivalents. Never include credentials, private business records, the
full batch review, raw page captures or the raw checkpoint. The helper projects
only referenced checkpoint step IDs, evidence basis and bounded capture metadata;
the request contains the model's selected sanitized explanations. Existing sealed
technical packs retain their separate content and transfer review requirements.
These checks are not automatic anonymization. The selected model sees the material
it reads/writes; only the reviewed sanitized export is intended for Fabio.

```bash
python scripts/development_request.py prepare --input <private-request.json> \
  --checkpoint <known-checkpoint-directory> --output <fresh-private-review-directory>
```

`--checkpoint` and `--developer-pack <sealed-pack-directory>` are optional. Keep
outputs outside the repository and published folders. Read `RICHIESTA.md` and
all listed JSON/technical attachments, resolve any private content or unsupported
claim, then show the operator the concrete summary and exact attachment list.
Do not set approval on their behalf. If the content changes, prepare a fresh
review directory and obtain approval for that version. Reuse an explicit approval
only when it covers these exact contents and intended recipient.

Say, for example: “Ho preparato il riepilogo di ciò che ha funzionato, il lavoro
richiesto e le prove disponibili. Questi sono i file che riceverà Fabio.” Ask only
for the missing transfer/content approval, not a new technical questionnaire.

## One ZIP, ready to send

After the operator reviews and approves the exact package, use the returned
`review_sha256` and a reference to their actual approval:

```bash
python scripts/development_request.py export <review-directory> \
  --review-sha256 <exact-reviewed-hash> --approval-id <actual-approval-reference> \
  --output <new-private-path>/richiesta-sviluppo.zip
python scripts/development_request.py verify <new-private-path>/richiesta-sviluppo.zip
```

Return one clickable ZIP link: “Questo è il file da mandare a Fabio.” Do not
send a directory of files, ask the operator to zip it, or claim it was sent.
The archive includes the human-readable request, structured request, source
fingerprints, optional reviewed developer pack and exact export approval. It
excludes unrelated files and rejects edits after review. Original artifacts stay
untouched. Export is not execution, capability-authoring approval, development
completion or a guarantee of portability.

## Optional CR registration

If the operator explicitly asks to transmit the prepared sanitized request to
Mparanza, show the exact `request.json` and identify `https://mparanza.com` as the
destination. After permission for that transmission, use Vera's existing
`scripts/change_requests.py submit-suggestion --request <review-directory>/request.json`
from the Vera root. It creates a capability request, not a fabricated failure.
Do not run the feedback survey, cooldown prompt or interview for this explicit
request. Report only the actual returned `CR-N`; a local `request_id` is never a
server CR number. Preserve the receipt beside, not inside, the frozen review
folder. Retries reuse that same request. This API transmits the structured text,
not the ZIP: do not claim attachments were uploaded. Return the ZIP separately
for the agreed channel. Never email or message Fabio without explicit sending
authorization. Do not mark the CR resolved merely because a handoff was exported.

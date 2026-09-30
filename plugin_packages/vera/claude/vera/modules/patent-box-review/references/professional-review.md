> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Authenticated professional review

The local adapter checks an externally signed review request and an externally
signed, client-specific mandate. It does not create keys, issue mandates, sign
for a professional, certify professional registration, or infer powers from a
name or certificate subject. Host sign-in and a typed reviewer name remain
separate from this authorization path.

## Firm configuration

A firm administrator configures `VERA_PATENT_BOX_AUTHORITY_CONFIG` once, outside
the case output directory. Its JSON has exactly `policy`, `openssl`,
`trusted_roots` and `crls`. Paths are absolute and point to reviewed host files.
`policy` follows `schemas/authority-policy.schema.json`: firm identity, pinned
administrator certificate fingerprints, synthetic/real separation, revoked
certificate fingerprints and revoked mandate IDs. An empty administrator set
cannot approve anything. No real firm policy is bundled or configured by this
implementation. The assistant must not create one to unblock a client run.

The administrator's externally signed mandate follows
`schemas/professional-mandate.schema.json`. It identifies the professional's
certificate fingerprint, professional reference, supporting powers evidence,
exact client/engagement/fiscal period, validity interval and permitted actions.
The firm is responsible for establishing these facts before issuing the mandate.
The adapter verifies that the pinned administrator signed those exact bytes;
it does not independently query a professional register or validate the legal
meaning of the supporting evidence.

## Case review

1. Complete the selected-evidence proposal and a public source scan. Every rule
   source must match an acquired original by ID and hash. Declared scan coverage
   must be complete, acquisitions at most 24 hours old, and the scanned source
   population must match the rules. Full legal coverage remains a model-led,
   professional judgment; byte equality does not establish legal applicability.
2. Run `prepare-professional-review --digest <proposal digest> --source-scan
   <scan directory>`. Show the exact proposal, sources, controls, amounts and
   unresolved issues. The output `request.json` binds client, engagement, period,
   run, selected evidence, proposal, rules and source preflight. It expires after
   24 hours. The professional reviews the readable material and signs these exact
   bytes using their chosen external signature service. The assistant never
   performs this signature or invents a review confirmation.
3. Run `accept-professional-review --digest <proposal digest> --request-digest
   <request digest> --signature <detached DER CMS> --mandate <mandate JSON>
   --mandate-signature <detached DER CMS>`. It verifies both signatures,
   certificates, explicit roots, current full-chain CRLs, digest/key-use policy,
   exact authority scope and revocation state. Control review also requires the
   mandate's REVIEW_RULES action. The original signed bytes, verification evidence
   and configuration snapshot are retained at a new path.
4. `calculate --digest <proposal digest>` rechecks the current mandate and source
   preflight before using this decision. A real run must be dated today. The
   engine separately requires reviewed, applicable and current rules and exact
   source/evidence bindings. Bundled real rules remain DRAFT; never relabel them
   to bypass professional interpretation or source review.
5. After reviewing the resulting documents, prepare another request with
   `--action APPROVE_DOSSIER`. This request also binds every generated artifact,
   result and earlier authenticated control decision. It needs another actual
   professional signature. Changed output bytes, inputs, rules, authority policy
   or stale source preflight require a new review version. Earlier records are
   never overwritten.

The stored approval is a signed professional statement for an exact version.
It is not a qualified signature on the dossier itself, statutory conservation,
a trusted timestamp, automatic penalty protection or confirmation of tax filing.
Local exclusive writes prevent workflow overwrite; independent retention against
privileged deletion and a production trust/mandate administration procedure still
need acceptance. Cryptographic receipts remain synthetic when their policy and
case are synthetic. Real-case and professional UAT remain outstanding.


## Controlled reopening

An approved version cannot authorize a different proposal. Prepare a new proposal,
then call `prepare-professional-review --action REOPEN_CASE --digest <new proposal>
--previous-digest <preserved proposal> --reason <actual reason> --source-scan <fresh scan>`.
Show the reason, the earlier version and the new scope/controls before obtaining
an actual signature. Accept it using `accept-professional-review`. The current
mandate must explicitly permit REOPEN_CASE. The signed request binds the new
proposal, sources, evidence, selected previous result, approval record and the
population of prior selected approvals. It does not approve the new controls or
outputs: run the separate control review, calculation and final review again.

For a completed archive run, prepare a new `patent-box-review` run in the same
client engagement. Explicitly select the earlier run's sealed artifacts as
`upstream_artifacts`, using their exact run/artifact IDs, plus the current case
inputs. The earlier session, proposal, authenticated decision, final approval,
calculation directory, final request/preflight and retained signature/mandate
receipt files must be included; selecting all its sealed output artifacts is a
supported conservative handoff. The archive validates the earlier manifest and
copies only the selected bytes into the successor run. The adapter does not
search another client folder or read unselected earlier paths. Use a new run
when inputs or the real calculation date change. Missing or changed upstream
artifacts block reopening. A closed engagement must first be reopened through
its own authorized archive process; this helper does not change that state.

Earlier approval signatures are checked for exact signed-byte integrity. The
historical certificate trust/time and statutory retention are labelled NOT_TESTED;
a local receipt date is not used as a trusted historical timestamp. Historical
mandates grant no new authority. The fresh, current certificate and firm mandate
must authorize the new reopening decision. The prior artifacts remain unchanged.

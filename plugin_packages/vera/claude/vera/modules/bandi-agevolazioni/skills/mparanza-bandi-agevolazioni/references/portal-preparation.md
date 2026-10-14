> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Approved portal preparation

After the user approves the project and asks Vera to compile the application,
Vera may fill ordinary fields, upload the exact approved attachments and save a
draft. Existing explicit approval in the conversation is sufficient; do not
request it again per field, upload or draft save. Approval of a project alone
without a request to act on the portal is not authorization to write externally.

Use the current host's available browser tools in the application authenticated
by the user. No bundled portal driver is provided. If these tools cannot write,
state that actual capability limitation and provide the field map; do not claim
that the bandi workflow prohibits approved compilation. Never obtain or record
credentials, cookies, tokens, one-time codes or signatures.

Before writing, identify the correct official destination, applicant, call and
application draft. Match the approved project, reviewed ordinary field values
and exact attachment files to the visible portal. Do not infer new amounts,
commitments, declarations or answers. Ask only for missing information or a
material change outside the existing approval. Fields marked `manual_only`,
including declaration and signature controls, remain manual. Submission controls
stay empty in the field map and cannot be activated during preparation; their
separate execution is governed by the final approval below.

The model must inspect each control's actual effect from the visible context.
Never operate authentication, declaration acceptance, signature, payment or
unapproved submission controls. A button combining save with submission requires
final submission approval even if its label contains "save"; a control also
accepting a declaration remains manual. If the effect is
unclear, stop before that control. Ordinary field autosave is allowed within
the approved destination and scope. Do not use keyword rules to decide effects.

Enter approved ordinary fields, upload only approved attachments, and use a
save-only draft action when available. Read the resulting values and attachment
list back, inspect validation messages, and verify the displayed draft state.
If a save has an uncertain result, inspect before retrying; do not duplicate
uploads or overwrite an existing different application. Stop on a mismatch.
Never claim the draft was saved or complete without visible supporting evidence.

Keep the private run record truthful. Before the first write, retain the user's
existing approval, destination (without query strings or session data), exact
approved values and attachment hashes in the run's review notes. Compute the
approved dossier scope with `record_review.current_scope_hash(output_dir,
run_id=run_id, scope="dossier")`. After an attempted preparation action, set
`run_state.json.portal_actions_performed=true` and record `portal_preparation`:

- `approved_by`: the user/professional reference, locally asserted;
- `confirmation_basis`: `explicit_user_confirmation`;
- `approved_scope_sha256`: the approved dossier scope hash;
- `destination`: the official HTTPS portal path without query or fragment;
- `actions`: records with `action` (`fill_field`, `upload_attachment` or
  `save_draft`), `target` and `observed_result`, including failures or uncertainty.

Use the running Studio Archive output boundary. These are operator-attested
records, not an authenticated browser trace or a runtime authorization engine.
A changed dossier invalidates the scope binding: obtain approval for its changed
content before further writing and preserve the prior action history in the
private review notes. Revalidate and repackage after updating run state; the
package's existing artifact hashes detect post-validation changes. Leave
`ready_to_file` and `signature_actions_performed` false. During preparation keep
`submission_actions_performed=false`. Report fields entered, attachments uploaded,
actual draft-save outcome, unresolved items and the next action.


## Final submission after explicit approval

Project approval and approval to compile do not authorize submission. Once the
application is complete, show the actual final portal summary: applicant, call,
application identifier, key project values and requested amount, exact attachment
list, remaining warnings and the effect of the final control. Resolve outstanding
items and let the user perform declarations, signature and payment where needed.
Ask for explicit authorization to submit this exact final application. Reuse an
explicit approval already given for this unchanged final summary; never ask twice.

Before clicking, record `submission_approval` in `run_state.json` with `approved_by`,
`confirmation_basis=explicit_final_submission_confirmation`, the current approved
`approved_scope_sha256`, the official `destination` without query/fragment,
`final_review` (the exact summary shown and approved) and `observed_result`
(initially "not attempted"). Identity and approval remain operator-attested.
If the application, attachments, destination or final control effect changes,
stop and obtain approval for the changed final version. A submission control
that also accepts declarations, signs or pays must still be handled by the user.

Use available host browser tools to execute only the approved submission. Record
an attempt truthfully with `portal_actions_performed=true` and
`submission_actions_performed=true`, and update `observed_result` even on failure
or uncertainty. For a user-prepared draft, no `portal_preparation` is required.
Read the resulting status and receipt/protocol number; save available confirmation
in the private run output and report it. A click alone is not proof of submission.
If the result is uncertain, inspect status/receipts before any retry; do not submit
a duplicate. Keep the attempted state and report uncertainty when unverified.
Revalidate and repackage the updated records. `ready_to_file=false` remains a
limit of automatic dossier validation, not a prohibition on user-authorized filing.

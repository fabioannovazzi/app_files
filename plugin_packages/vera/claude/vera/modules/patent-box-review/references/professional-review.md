> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Confirmation of the exact Patent Box proposal

Show the complete selected proposal, current sources, control choices, amounts,
open issues and readable review. Ask the user whether these specific choices are
okay and whether to proceed. Reuse an actual confirmation for this same version;
never infer it from a general instruction to develop software or from a test.

1. Run `prepare-review --digest <proposal digest> --source-scan
   <scan directory>`. The retained request binds the run, scope, proposal, sources
   and reviewed rules. Read `review.md` and the full proposal before confirmation.
2. After the actual user says yes, run `accept-review --digest
   <proposal digest> --request-digest <request digest> --reviewer <actual actor>
   --confirmation-ref <actual message reference> --confirmed`.
3. Run `calculate --digest <proposal digest>`. It verifies the saved decision,
   current source scan, source bytes and the exact proposal. Missing confirmation,
   changed sources or an obsolete version remain blocked.

The command names are retained for compatibility. This is a local record of a
user decision, not professional sign-off or authenticated identity. There is no
required professional role, authority configuration, certificate, signature or
mandate. Do not create or request any to continue ordinary work.

After showing the generated dossier, `--action APPROVE_DOSSIER` can record the
user's decision on those exact artifacts. For a material revision use
`--action REOPEN_CASE --previous-digest <retained version> --reason <actual reason>`
and obtain confirmation of the new proposal. Preserve the previous version and
its history. New sources still require the ordinary source-bound Archive route.

Inspection of signatures on documents actually supplied by the user is a
separate optional function. It neither signs documents nor imposes an approval
signature on calculations or draft export.

> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Deliver the budget report through Sites

Run the normal inspection, reviewed mapping, calculation and metric-linked
commentary workflow first. Show the local HTML and disclose remaining missing
sections and its professional-review status. Preserve both amount and percentage
variances and the shared IBCS-style reporting table; browser selections only
reveal already calculated period/scenario views. With scripts disabled, all
views remain visible. Printing includes the selected view.

Prepare a fresh candidate from the persisted pack and the same exact inputs:

```bash
python scripts/prepare_report_site.py --input <exports.xlsx> --recipe <reviewed-recipe.json> --pack <management_control_pack.json> --commentary <commentary.json> --audience <client> --client-engagement <context.json> --output-dir <new-site-folder>
```

Repeat `--input` for separate files. Commentary is optional. Vera retains its
Studio Archive input and output binding. The helper replays the complete pack,
checks audience equality, rejects blocked or unsupported budget reports and
refuses to overwrite an earlier candidate. It writes the exact rendered HTML
in `dist/index.html`, a static `.openai/hosting.json`, and a local delivery receipt.
It performs no upload. The receipt is not in the public output.

Use the available Sites building/hosting capabilities to publish this static
source unchanged. The whole HTML reaches Sites: entity, all financial comparison
views, coverage/limitations, authored commentary and optional customer/supplier
or service labels. Hidden views remain delivered. Original export files, raw
source populations, local paths and the complete pack JSON are not copied into
`dist`. No automatic redaction is performed. Hosting, visitor access, retention
and deletion depend on the selected Sites service/account.

An explicit Sites request selects this route. Confirm only unresolved audience
or sharing decisions and honor host-required action approvals. Verify deployment
success and intended visitor access before handing over the link. Do not send
invitations without authorized recipients. A public synthetic demo may be made
public when requested; do not transfer that permission to a customer report.

For a refresh, retain the previous run, inspect changed inputs, review changed
mappings and assumptions, recalculate and prepare a fresh candidate. Reuse the
existing Site ID and explicitly publish the new version. This is an explicit
refresh; recurring monitoring requires a separate user request.

> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Publish the existing financial report through Sites

Use the same report in Vera and Clara. The workflow prepares a static Sites source
from the validated report; Sites supplies hosting and visitor access. It does not
require another financial renderer, database or financial calculation service.

1. Resolve the exact persisted `business_plan.json`, its original source root and
   the intended audience. Check that the report is the user's current iteration.
   If its audience is internal and the user wants client sharing, prepare a new
   report for that client audience using the existing source-audience decisions.
   Keep the prior report. A changed audience is not an automatic release of
   internal-only evidence. Retain pending review and material assumptions.
2. Run the normal dependency check, then prepare a fresh publication candidate:

   ```bash
   python scripts/prepare_report_site.py \
     --plan <run-output>/business_plan.json \
     --source-root <original-run-input-dir> \
     --audience <report-audience> --output-dir <new-site-candidate>
   ```

   The helper replays the plan, input hashes, figures and audience restrictions,
   rejects blocked reports, and writes the exact compiled HTML to `dist/index.html`.
   `site_delivery.json` records the report hash and preparation status outside the
   public directory. The local candidate is not evidence of publication.
3. Inspect the report before delivery, including all comparison views, their
   captions and the intended reader's source material. All precompiled views,
   the technical appendix and embedded case workpapers are included in the HTML.
   Collapsing or filtering them does not remove them from the delivered file.
   The original source files are not copied as separate public downloads, but
   their selected content, filenames and relative paths remain in the report.
4. Use the installed Sites building/hosting skills and tools on this existing
   static source. Preserve it; do not scaffold a replacement dashboard or paste
   its figures into a new page. Reuse a registered Site's exact `project_id`; for
   first publication register once and persist the returned ID in
   `.openai/hosting.json`, retaining `static.directory: "dist"`.
5. Push only this Site's source, package its configured public output, save and
   deploy it through Sites. Follow the host's actual access and approval checks.
   For a first preview use private owner access. For requested client delivery,
   resolve the named recipients and intended access; external invitations depend
   on the account's Sites availability. A public URL or successful private
   deployment alone does not prove the client can open it. Do not invite or
   message people outside the user's authorized recipients.
6. Verify terminal deployment success, the reported live URL and the intended
   access setting. Keep a local delivery record with Site ID, saved version,
   deployment result, audience, report hash and live URL. Return the report link
   and a short finding. State any remaining sharing blocker precisely.

For a refresh, rebuild a new persisted report from the changed evidence, reassess
its conclusions, prepare a fresh candidate, and publish it to the same Site with
its existing access. Preserve earlier report folders and delivery records. Do not
reuse old professional approval for revised figures. Schedule this only when the
user requests recurring updates; the hosted report does not run a schedule.

Period/scenario controls reveal already compiled comparisons. They do not change
assumptions, issue financial advice, call a model or send data over the network.
Browser printing includes the selected views; the compiler's optional PDF export
includes every comparison view. The HTML remains readable with JavaScript off.

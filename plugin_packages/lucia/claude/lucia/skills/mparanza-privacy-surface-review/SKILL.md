---
name: mparanza-privacy-surface-review
description: Review Vera, Clara or Lucia source, model-context paths, external services, public explanations and run-report contracts before releasing a product workflow.
---

# Privacy surface review

This developer workflow is identical in Vera, Clara and Lucia. It does not add a
customer intake, a consent questionnaire or a professional process to usage
counts. Ordinary authorized model processing follows the selected host account.

1. Resolve this installation's product root and read `privacy/registry.json`,
   `components.json` and `privacy/runtime-profiles.json`. Inventory every exposed
   skill, embedded component, primary process and service. Studio Archive is
   infrastructure. A direct skill must not escape review merely because it has
   no embedded component. A registration alias maps an existing process; it does
   not create another rated task.
2. Read the selected complete skill, its references, relevant scripts, schemas,
   model-visible payload builders, connectors and native or hosted routes.
   Resolve a product source inside its root; resolve components in `modules/`
   when installed or in the sibling repository component. Follow cross-component
   dependencies. Inspect actual emitted payloads and app-only metadata separately.
3. Describe information that can enter the selected host model context, with its
   purpose and source. Names, identifiers, full documents and professional facts
   can be necessary. Local calculations do not imply a local-only conversation
   or automatic anonymization. Do not infer a provider or account configuration
   from an operating system or a product name. Antigravity uses the provider
   actually selected in that host; its package alone does not identify the model.
4. Record every additional boundary: public retrieval, hosted service, connector,
   and send/publish action. Reuse shared `privacy/services/` records through
   `service_ids`. Preserve actual recipients, payloads, returned data, activation,
   access, retention limitations and executable controls. A route being optional
   does not mean it ran. Prior authorization applies only to the same scope and
   only when the host permits it; never override an action-time approval or denial.
5. Review each supported host route separately. Availability of local Python,
   native UI, connected files and saved state differs. Explicitly record missing
   capabilities; never claim a local helper executed in a chat-only host. The
   user's account controls training and retention; the plugin does not inspect
   or enforce them. Do not invent a per-case account form.
6. For every registered public page, author its localized `public_explanations`
   in the governing workstream manifest. Explain that function's actual data
   path in plain language. The generated page uses this exact reviewed copy and
   contract revision, selected by product and page. Keep “Quali dati arrivano al
   modello” (localized) as the final process section. If the review is incomplete,
   retain an explicitly labelled localized placeholder; never borrow another
   function's behavior. `not-relevant` requires an evidence-based explanation.
7. Read `references/model-data-report-contract.md`. The reviewed contract says
   what can happen; the saved report says what happened. Review actual phase
   evidence, identify deviations and unknowns, and record the semantic comparison.
   Never fill actual counts or phases from this manifest. A contract digest is
   not proof of model-provider transmission or professional correctness. Old
   reports and their signatures remain verifiable without today's installation.
8. Update `privacy/workstreams/<id>.json` or `privacy/services/<id>.json` only
   after inspecting the governed source. Refresh the selected fingerprint with
   the commands below. The refresh performs hashing, not semantic approval.
9. Validate the complete register, regenerate contract/public artifacts and run
   their drift checks. Rebuild every product/host affected by a shared change.
   Review actual packaged manifests and preserved source declarations; package
   validation is not evidence that a remote hosted service was deployed or tested.
10. Exercise a synthetic workflow with a fresh supported session, show the actual
    readable report by default, reopen it without rerunning the task, and verify
    the retained signed receipt. Record the exact host, version and remaining
    acceptance limits. Do not label CLI-only evidence as host-conversation proof.

```bash
python skills/mparanza-privacy-surface-review/scripts/validate_privacy_surfaces.py --refresh <workstream>
python skills/mparanza-privacy-surface-review/scripts/validate_privacy_surfaces.py --refresh-service <service>
python skills/mparanza-privacy-surface-review/scripts/validate_privacy_surfaces.py
```

Repository generation and release:

```bash
python scripts/sync_privacy_runtime.py --check
python scripts/build_privacy_contracts.py --check
python scripts/build_product_release.py --check
```

## Judgment boundary

Code checks schemas, explicit registrations, file identities, source freshness,
translations present, exact contract bindings and package bytes. These are
mechanically verifiable. The host agent judges relevance, adequacy, actual data
exposure and the accuracy of the explanation from inspected evidence. Do not
implement keyword privacy classifiers or automatically delete or anonymize
professional facts. Empty external-boundary/security-control arrays are valid
when supported by source. A policy statement is not an executable control.

This register is engineering evidence, not legal advice, a DPIA, a provider
account audit or a certification of GDPR compliance.

Read `references/public-process-page-contract.md` for the final HTML section.
Honor an existing user choice only where the host permits prior authorization;
it never overrides action-time confirmation or a denied operation. Do not invent
per-run consent for the already authorized technical reporting route.

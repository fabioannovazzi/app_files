---
name: privacy-surface-review
description: Use when adding, changing, reviewing, or releasing a Clara workflow or hosted integration to record what Codex can read, every boundary beyond Codex, and the source-backed access and retention position before packaging.
---

# Privacy Surface Review

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../clara/SKILL.md`.

Do not initiate feedback merely because this release check was run.

This is a developer and release workflow. It is not a customer-case intake step.
A normal Clara run does not display a privacy notice or ask for privacy consent
merely because Codex reads professional material.

## Review workflow

1. Resolve the Clara root and list every sibling directory in `skills/` that has
   a `SKILL.md`. Every user-facing workflow except this review skill must have a
   matching record in `privacy/workflows/`.
2. Read the workflow's complete skill and every relevant script, reference,
   payload builder, connector, browser route, and embedded component. For
   Attribute Reporting and Brand Fit, resolve `modules/attribute-reporting` in a
   packaged plugin or the sibling repository component.
3. Record the information that may enter Codex context. Real client, participant,
   employee, source, transcript, deck, and business data may enter that context.
   Do not describe model-read material as local-only because its source file or
   final artifact remains on the user's computer.
   For ordinary Codex model processing, keep the common policy explicit: the
   user-selected ChatGPT/Codex account is the processing arrangement; Clara adds
   no separate recipient, does not automatically anonymise, and may filter or
   aggregate locally only when useful. Clara cannot inspect or enforce the plan.
4. Record every boundary beyond Codex in the workflow manifest. Link every
   Mparanza route to one record in `privacy/hosted-services/`. Public research,
   public image retrieval, external connectors, and send or publish actions stay
   in the workflow manifest.
5. For a hosted service, record only payload, access, and retention facts that
   inspected governed source supports, including the relevant Mparanza service
   and legal copy. If those sources do not establish hosted retention or
   deletion, say so. Link expiry is not proof that stored material is deleted.
6. The user's explicit choice of a hosted, connector, send, or publish route is
   the confirmation for that route. Ask separately only when the external action
   is optional and the user has not already chosen it. Do not ask twice.
7. Record only source-enforced security controls and the user's ChatGPT/Codex
   account boundary. An empty security-control array is accurate when the
   workflow has no control of its own. Do not relabel local storage, output
   review, source preservation, ordinary route choice, policy wording, or a
   procedural instruction as security. Clara cannot inspect or enforce the
   user's plan, model-training data controls, or retention/deletion controls. The
   firm or user checks those before professional use and when the account or
   terms change, not in a per-case form.
8. Update the workflow and hosted-service manifests, then refresh only after the
   substantive review is complete:

```bash
python skills/privacy-surface-review/scripts/validate_privacy_surfaces.py \
  --refresh <workflow-or-service-id>
```

9. Validate the complete register and run the Clara privacy tests before
   packaging:

```bash
python skills/privacy-surface-review/scripts/validate_privacy_surfaces.py
pytest -q tests/plugins/test_clara_privacy_surfaces.py
```

## Judgment boundary

Use deterministic code for registered-workflow coverage, JSON shape, allowed
boundary kinds, hosted-service references, confirmation consistency, exact file
hashing, and stale-review detection.

Do not add automatic anonymisation, personal-data detection, deterministic
deletion, a `minimum useful context` classifier, per-prompt declarations, or
routine consent screens. Local Python may filter or aggregate information when
that improves the professional work; that is not a claim that everything read
by Codex was anonymised.

This register is an engineering record. It is not legal advice, a DPIA, an
account-configuration audit, or a certification of GDPR compliance.

## Codex-Native Run UX

Keep a short developer checklist for workflow coverage, hosted-service coverage,
source review, fingerprint refresh, schema validation, and focused tests.

Before source review, show a compact Run Intake table with the changed workflow
or service ID, governed paths, related manifests, and whether the change adds or
alters a boundary beyond Codex. Show a Decision Table only when source evidence
leaves a real boundary, access, or retention fact unresolved; record an unknown
instead of guessing.

Default output policy: update the affected manifest, refresh its fingerprint,
and validate the complete register. These are not choices to propose when the
user asks for the normal privacy-surface review.

Before refreshing fingerprints, use one execution checkpoint naming the changed
workflow or service, governed paths, and manifests. Never edit generated ZIPs by
hand; release artifacts are rebuilt from source.

End with an Artifact Card listing the validated register, any intentionally
unknown hosted arrangement, and the test result. Create `codex_run_review.md`
only when the review needs a local note about blocked source evidence, a schema
gap, or repeated manual cleanup. Do not create customer-facing notices or case
artifacts.

> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Workflow method

## 1. Establish evidence

For a refresh, capture the current website at the reference date and distinguish
what was actually observed from what is proposed. For a first site, inventory
the studio facts, selected prior communications, logo, photography and contact
details supplied for public use. When the professional supplies a fact directly
in chat, record the exact confirmed statement as immutable intake evidence; do
not require them to create a document. A public URL is not a durable source
snapshot. Include a source only after the professional approves it for the
website purpose; that approval does not make every statement in the
source accepted website copy.

## 2. Map post-brief source use

The model records one `source_use_plan` entry for every selected evidence ID.
State the professional purpose and choose the narrowest purpose-preserving mode:

- `mapped_brief_only`: the mapped facts and decisions are sufficient;
- `targeted_material`: later work needs only named excerpts, pages, sections,
  assets or code paths;
- `full_source_required`: the complete source remains necessary for one stated
  professional reason.

After the brief is recorded, design, copy, implementation and quality work use
the brief plus only the material allowed by this plan. Reopen a complete source
only for its recorded reason. Source-ID coverage and schema shape are
mechanical checks; professional purpose and relevance remain model-led.

## 3. Establish the reader's decision

Identify the smallest set of questions the website must answer:

1. Who is this professional or studio?
2. Whom do they help?
3. What work do they actually perform?
4. Why is the professional credible?
5. What should the visitor do next?

Do not turn the site into a list of every possible service or a biography with
the useful information buried below it.

## 4. Propose a studio profile

Record each identity field with one basis:

- `observed`: present in selected existing material;
- `user_supplied`: explicitly provided for this website;
- `vera_default_proposal`: a conservative first proposal.

Default proposals may cover typography, spacing, restrained colors, page
geometry and voice. They may not create facts, reputation or history.

## 5. Build the working site

Prefer a small semantic HTML/CSS implementation with minimal JavaScript. Use a
framework only when the host platform or requested behavior justifies it.
Preserve simple deployment and future editing. Localize approved assets when
the license and platform permit it. Forms, embedded third-party applications and
remote executable scripts require a separate integration scope and must not pass
as ordinary informational-site content.

## 6. Review exact bytes

Run mechanical validation, then inspect the rendered site at desktop and phone
widths. Preserve a full-page PNG whose pixel width matches each claimed viewport
and bind its path and hash to the assessment. Review identity and claims,
responsive behavior and destination separately. Bind every decision to the
current evidence, brief, site, validation and quality-assessment digests; any
changed dependency invalidates stale acceptance.

## 7. Publish deliberately

An unlisted preview is a published website that anyone with the link can open.
Use a hard-to-guess path, add `noindex, nofollow, noarchive`, avoid public navigation and publish only
after that route was selected. Remove preview robots directives before release,
then revalidate and review the changed bytes. Final publication requires
explicit approval of the exact package and destination.

OpenAI Sites is unavailable for new Cowork publication. When supplied artifacts
already name Sites, review their package, binding, archive, version and deployment
receipts as evidence and keep publication pending unless that exact evidence proves
a succeeded deployment.

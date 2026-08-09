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
details supplied for public use. A public URL is not a durable source snapshot.

## 2. Establish the reader's decision

Identify the smallest set of questions the website must answer:

1. Who is this professional or studio?
2. Whom do they help?
3. What work do they actually perform?
4. Why is the professional credible?
5. What should the visitor do next?

Do not turn the site into a list of every possible service or a biography with
the useful information buried below it.

## 3. Propose a studio profile

Record each identity field with one basis:

- `observed`: present in selected existing material;
- `user_supplied`: explicitly provided for this website;
- `vera_default_proposal`: a conservative first proposal.

Default proposals may cover typography, spacing, restrained colors, page
geometry and voice. They may not create facts, reputation or history.

## 4. Build the working site

Prefer a small semantic HTML/CSS implementation with minimal JavaScript. Use a
framework only when the host platform or requested behavior justifies it.
Preserve simple deployment and future editing. Localize approved assets when
the license and platform permit it.

## 5. Review exact bytes

Run mechanical validation, then inspect the rendered site at desktop and phone
widths. Review identity and claims, responsive behavior and destination
separately. Bind every decision to the current site digest; any content or code
change invalidates stale acceptance.

## 6. Publish deliberately

An unlisted preview is still an external disclosure. Use a hard-to-guess path,
add `noindex, nofollow, noarchive`, avoid public navigation and publish only
after that route was selected. Final publication requires explicit approval of
the exact package and destination.

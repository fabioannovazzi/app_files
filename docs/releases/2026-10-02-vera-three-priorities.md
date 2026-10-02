# Vera 0.1.330: three professional entry points

## Change

Present Vera in this order: **Quesiti fiscali e legali**, **Bilancio**, and
**Revisione contabile e riconciliazioni**. These are product priorities chosen
by Fabio, not a measured ranking of request frequency.

The canonical manifest, its three starter prompts, the reviewed long-description
file and Cowork description now agree. The root skill explicitly selects the
existing complete `quesito-legale-fiscale` journey for fiscal/legal answers,
`bilancio-oic` for preparation and `financial-analysis` for analysis. Audit
support selects the requested reconciliation, sampling or document check;
it does not offer certification or a signed audit opinion.

Keep Vera's name, subtitle, all 73 canonical keywords, category, URLs, icons,
components and all 47 specialist/root skill identities. No analysis engine, tool schema, website
HTML, sitemap, robots policy or published-version notification changes.
Other supported functions remain available. Refresh only the six privacy review
fingerprints whose governed root metadata changed; external boundaries are
unchanged.

## Evidence limits

Current main had reverted the manifest to management-control and website
starters while its separate long-description file retained the earlier copy.
This change aligns them to the newly agreed priorities. The October 1 discovery
experiment tested earlier text; it does not evaluate this wording. Package
checks establish source fidelity, not ChatGPT ranking or recommendation effects.
No claim of improved or protected indexing is supported by these checks.

Marketplace publication, upload, submission and publication drafts are not
authorized and are not part of this change. Server deployment and package
availability do not establish that an installed plugin or existing conversation
has updated.

## Local validation

- Package, metadata, update-notification, icon, release-alignment, skill-identity,
  privacy and installed-product-checker suites: **494 passed, 2 skipped**.
  The two skips require locally installed curated Marketplace plugins that are
  unavailable. Four existing FastAPI lifecycle deprecation warnings remain.
- Separate release-alignment coverage: **13 passed; 98.44%**, above the 80% gate.
- `build_product_release.py --check`: Vera, Clara and Lucia match canonical source
  and versions. Vera is 0.1.330; all 18 Vera MCP servers initialize/list tools.
- Complete privacy register, Black/Isort on the changed test and `git diff --check`
  pass. A source comparison confirms all 73 keywords and all 47 skill identities
  are preserved.
- The accounting-discovery assertion now checks the existing canonical keyword
  `contabilita` independently of accented wording in the description. This does
  not assume that a search service normalizes accents.

These are source and package checks; no installed-host acceptance or public
recommendation experiment was performed for this candidate.

# Vera 0.1.206 implementation gate repair

Six module bootstrap scanners now ignore real `__pycache__` directories and ordinary single-link `.pyc`/`.pyo` files before comparing the exact implementation allowlist. Contract entries, source-file validation, symlink rejection and disabled bytecode execution remain unchanged.

Modules: journal-sampling, open-item-reconciliation, journal-bank-reconciliation, concordato-plan-review, report-builder and check-entries. Check Entries has the same bootstrap scanner with differently named contract roots.

Optional cleanup from the installed Vera root:

```bash
python3 modules/<module>/scripts/implementation_bootstrap.py --repair
```

This first validates the tree, then deletes only ordinary single-link `.pyc` files directly inside `__pycache__` folders under the module's own vendor tree. It retains directories and other files, skips links, and never falls back to a shared vendor root. Module and generated Cowork instructions explicitly prohibit hand-editing installed plugin trees or bypassing permission rejection after an integrity mismatch.

Validation: 54 new regression cases across all six modules; 70 focused cases including retained malicious-bytecode execution checks passed on the isolated release checkout. Codex/Cowork ZIP drift checks passed and all 18 packaged MCP servers initialized and listed tools. Fresh synthetic archive intake, managed inspection and reviewed normalization emitted two rows. An ambient import generated seven vendor `.pyc` files and the subsequent managed dependency check passed.

The original evidence files 13 and 14 establish an ambient import after a rejected ad hoc helper, unsafe manual deletion following permission rejections, and a clean inspection/normalization control. They do not establish a complete sampling run.

Scope limitation: separate Check Entries Node startup and Python receipt gates still reject bytecode; this release does not claim all MCP/receipt paths tolerate caches. Those additional gates are outside this six-bootstrap fix. Server/download deployment does not establish Marketplace publication.

## Finished-archive release gate

Every Vera Codex, ChatGPT upload, Cowork and Antigravity build extracts its final
candidate ZIP and runs the packaged `prepare_execution_root` API for all six
`ASSURED_MODULES`, using isolated Python with bytecode disabled. Any inventory,
content or module-bootstrap failure blocks replacement of the existing release.
The same gate runs in package `--check` mode and release-alignment CI. It calls
the preparation API directly so a deliberately broken release test cannot submit
customer operational incidents.

The Cowork index is sealed once after the final custom-skill-name projection.
Antigravity regenerates its index after removing host-specific files and adding
its manifest, agent and MCP configuration. Each index therefore describes that
host's final file bytes and inventory. No installed files or integrity checks
are repaired or bypassed.

These checks establish package consistency and execution preparation, not an
end-to-end accounting result or acceptance in a user's enabled host installation.

The ChatGPT skills-only projection also binds the four previously static module
contracts to that host's exact layout: omitted `.app.json`, `.mcp.json` and
`mcp/server.cjs` entries are replaced with the packaged local review helpers.
Journal-bank-reconciliation and report-builder already select their host contract
at runtime. The four projected scanners reject mixed native-host files, missing
helpers and unexpected scripts even when the outer package index is regenerated.


## Cowork frontmatter repair (0.1.389)

The affected local Cowork cache was inspected on 2026-10-15. Its manifest
reported 0.1.388 and exactly one of 1,699 indexed files differed:
`skills/mparanza-contenzioso-tributario/SKILL.md`. Compared with the public
archive, the cached file only added double quotes around `description`.
That exact change produces the reported `748d403d...` hash instead of
`932c878d...`.

The original description contains an unquoted colon followed by a space.
A YAML parser rejects the packaged frontmatter; the quoted installed variant
parses. This establishes a source-format defect and a post-package difference,
not evidence of two different public 0.1.388 builds. The precise host stage
that added the quotes was not observed.

The source description is now quoted before packaging and index generation.
CI parses every shipped skill entrypoint in all four Vera archives with
`yaml.safe_load`, requiring string name and description fields. This complements
the real execution verifier: matching digests alone do not prove the host can
parse the skills without repairing their bytes. Teaching content and legal
instructions are unchanged; their source bindings were refreshed explicitly.

A separate local launch failure was traced to `node` being absent from the
Claude application's logged search path. Making the already installed Node
runtime callable on that path allowed all 22 local servers in the affected
installation to complete initialize/tools-list checks. This environment repair
is separate from package integrity and does not prove a professional workflow.

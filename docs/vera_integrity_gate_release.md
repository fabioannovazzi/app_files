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

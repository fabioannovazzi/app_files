Totally fine—here’s the “press‑this‑button” version.

------

## The simplest way to run it

1. **Open a terminal.**

2. **Go to your repo root.**

   ```bash
   cd /path/to/your/repo
   ```

3. **Put the two list files in place** (one for app code, one for tests):

   ```bash
   printf "modules/\nsrc/\nui/\n" > modules_to_scan.txt
   printf "tests/\n" > tests_to_scan.txt
   ```

4. **Use the tracked Codex Makefile:** `tools/Makefile.codex`.

5. **Make the scripts executable** (one‑time):

   ```bash
   chmod +x tools/run_codex_*.py tools/scan_*.py
   ```

6. **(Recommended) Create a branch:**

   ```bash
   git checkout -b chore/codex-nightly-$(date +%F)
   ```

------

## Which command to run?

**Option A — run EVERYTHING (detectors first, then refactors):**

```bash
make -f tools/Makefile.codex nightly
```

- Detectors run **first** and write reports into `reports/`.
- Then all the refactor scripts run in the safe order we set.

**Option B — run ONLY refactors (skip detectors):**

```bash
make -f tools/Makefile.codex codex-refactors
```

**Option C — run ONLY detectors (no code changes):**

```bash
make -f tools/Makefile.codex detectors
```

Detector scripts (already generated):

- [scan_vectorization_candidates.py](scan_vectorization_candidates.py)
- [scan_ui_vs_logic_misplacements.py](scan_ui_vs_logic_misplacements.py)

**Where do detector reports go?**
 `reports/vectorize.{txt,json}`, `reports/ui_logic.{txt,json}`

------

## What happens when I run `nightly`?

- The **detectors** run **first** and always finish (they don’t fail the build).
- Then the **refactors** run in this order (top‑to‑bottom):
  1. Pathlib (detector‑only)
  2. Print→logging (detector‑only)
  3. Exceptions (detector‑only)
  4. Polars streaming arg rename (detector‑only)
  5. **Pandas→Polars** (**with `--all`**)
  6. Polars schema helper (detector‑only)
  7. Polars row/col counts (detector‑only)
  8. **LLM wrapper integration** (detector‑only)
  9. **Test gate** (`pytest -q`)
  10. **LLM naming** (detector‑only)
  11. **Test gate** (`pytest -q`)
  12. **Test repair** (**with `--all`**, on tests only)

This aligns with your project’s “green before merge” ethos (run tests, keep changes minimal). 

------

## Run it overnight (optional, but handy)

```bash
mkdir -p logs
nohup make -f tools/Makefile.codex nightly > logs/nightly_$(date +%F_%H%M).log 2>&1 &
tail -f logs/nightly_*.log
```

------

## Can I skip the detectors?

Yes—just run:

```bash
make -f tools/Makefile.codex codex-refactors
```

------

## Two friendly switches (you can ignore these for now)

- Stop at the **first** failing script:

  ```bash
  FAILFAST=1 make -f tools/Makefile.codex codex-refactors
  ```

- Make the overall target **fail at the end** if *any* script failed (but still run all):

  ```bash
  STRICT=1 make -f tools/Makefile.codex codex-refactors
  ```

------

## Tiny cheat‑sheet

| You want…             | Run                                      |
| --------------------- | ---------------------------------------- |
| Detectors + Refactors | `make -f tools/Makefile.codex nightly`         |
| Only Refactors        | `make -f tools/Makefile.codex codex-refactors` |
| Only Detectors        | `make -f tools/Makefile.codex detectors`       |

------

If you get stuck, you can do a dry run to see *exactly* what will execute:

```bash
make -n -f tools/Makefile.codex codex-refactors
```

And remember, tests are your safety net; your guidelines recommend running tests and keeping PRs green before merging.

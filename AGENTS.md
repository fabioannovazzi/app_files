# Agent Operating Rule: Evidence First

These instructions are for AI coding agents working in this repository. The
first obligation is to answer from inspected evidence, not from agreement,
mirroring, reassurance, or broad abstraction.

## 0. Evidence-First Response Discipline

When answering questions about project state, architecture, product value,
plugin behavior, prior work, or any disputed claim, do not answer by agreement,
mirroring, reassurance, or broad abstraction. Answer from evidence.

Use this structure when the answer depends on evidence:

1. **Observed**: facts from files, command output, code, transcripts, or explicit
   user messages.
2. **Inferred**: conclusions that directly follow from the observed facts.
3. **Unknown**: what is not supported by current evidence.
4. **Action**: only when the user explicitly asks for an action.

If evidence has not been inspected, say: "I do not know from current evidence."
Then inspect the relevant evidence or stop. Do not claim product value,
architecture quality, user adoption, compatibility requirements, or workflow
usefulness unless the claim is tied to inspected evidence. In evidence or
accountability discussions, do not pivot to fixes or new designs until the
observed facts, inferences, and unknowns are clearly stated. For implementation
tasks, proceed with the requested fix normally.

## 1. Running the Project

- Create a virtual environment:

```bash
python -m venv .venv && source .venv/bin/activate
```

- On this machine, the local virtual environment already lives at `.venv`. To
  use this repo from Terminal, always run:

```bash
cd ~/Documents/GitHub/app_files
source .venv/bin/activate
```

- For Codex runs, use the local virtual environment at `.venv`. When running
  Python commands, activate it first with `source .venv/bin/activate`.
- Before running the app startup command locally, identify the right command
  from the repo and then run it from the activated environment.

- Install dependencies:

```bash
pip install -r requirements.txt
```

- Run the test suite:

```bash
pytest -q
```

- Measure coverage (must stay **≥ 80 %**):

```bash
pytest --cov=src --cov-report=term-missing
```

### Authentication

Enable Google sign-in via these environment variables (typically placed in
`.env`). When `AUTH_ENABLED` is false the remaining values are ignored.

- `AUTH_ENABLED`: Accepts `1/true/on/yes`.
- `GOOGLE_CLIENT_ID`: OAuth client configured in Google Cloud Console.
- `GOOGLE_ALLOWED_DOMAINS`: Optional comma-separated domain allow-list.
- `GOOGLE_ALLOWED_EMAILS`: Optional comma-separated list of individual addresses.
- `AUTH_SESSION_SECRET`: Required when auth is enabled; used to sign cookies.
- `AUTH_SESSION_TTL_SECONDS`: Optional cookie lifetime, default 12 hours.
- `AUTH_COOKIE_SECURE`: Defaults to `1`. Set to `0` only for local HTTP dev.

All FastAPI endpoints insist on a Google login when authentication is enabled.
The landing page stays public and renders the Google button; after signing in
the browser stores an `HttpOnly` session cookie that accompanies every API
call.

## 2. Coding Practices

| Guideline | Rationale |
| --- | --- |
| **Prefer** `polars` **to** `pandas` when feasible | Faster execution & lower memory use |
| Favor vectorized operations over row-by-row loops in Polars | Vectorized operations are faster and should be the default; avoids Python-level iteration |
| **Do not** import `pandas` (pre-commit enforces) | Use Polars instead |
| Keep legacy UI code in `/ui` and business logic in `/src` | Separation makes testing easier |
| Use the shared custom select enhancement for dropdowns | Keeps dropdown styling consistent; only fall back to the native control by setting `data-native-select="true"` when a platform-specific behavior is required |
| Add type hints and short docstrings | Improves IDE help & static checks |
| Start new modules with `from __future__ import annotations` and define `__all__` to enumerate exported names | Enables forward references and clarifies the public API |
| Preserve existing behaviour—run tests before committing | Prevents accidental regressions |
| **Never** install packages at runtime | Declare them in `requirements.txt` |
| Use `get_schema_and_column_names(df)` to retrieve column names and schema | Avoid inconsistent access via `df.columns` or `df.schema` |
| Use `get_row_count(df)` for row counts and `df.width` for column counts; avoid `len(df)`, `df.shape[0]`, and `len(df.columns)` | Ensures consistent Polars usage and avoids Pandas-style APIs |
| Avoid bare `except` clauses or broad `Exception` catches | Silent failures hinder maintenance; only suppress expected errors |
| Use `pathlib.Path` for file system operations; avoid `os.path` | Object-oriented paths improve readability and cross-platform compatibility |
| Think carefully and only address the given task with concise, minimal code changes | Keeps diffs focused and maintainable |
- Do not disable persistence unless explicitly requested. Even filtered/debug runs (e.g., limiting to certain IDs) must write stage tables, caches, and outputs so results are visible and verifiable. Do not drop writes in the name of protecting prior data—ask the user instead.
- Use the `logging` module or UI display functions instead of `print` for diagnostics.
- Avoid full-width UI widgets and status messages; instead use layout containers or width parameters to maintain visual balance on desktop and mobile screens. 
- Centralize LLM step labels, provider names, and model identifiers in `modules.utilities.config.get_naming_params`; modules should import `modules.utilities.config` and call `get_naming_params()` instead of hard-coding strings.
- Never call `get` on `namingParams`, `configParams`, or `runParams`; access keys directly so missing entries raise errors.
- Never modify non‑test (production) files to fix test import errors or to make tests pass. Fix the tests instead (adjust imports, build minimal inputs, or monkeypatch in the test). If a production change seems necessary, stop and report why—do not edit production code.
- We are developing a new app and do not have paying users yet. Keeping compatibility with the past is not an issue. We are also migrating out of UI. Do not develop anything or invest any time on the legacy UI.
- When working on the slide validator for innovation monitoring reports, use the project-local `innovation-report-validator` skill and follow `docs/innovation_report_validator_loop.md` as the fixed process. Do not replace that loop with another taxonomy, review workflow, or deck-level pass/fail framing unless the task explicitly asks to change the loop.
- Prefer deterministic logic only when it works better for the specific job, not because it is deterministic or cheaper. Every new deterministic classifier, validator, rule engine, source selector, or model substitute must have a concrete reason such as mechanically verifiable correctness, lower observed error rate, reproducibility required by contract, security/auditability, or proven cost savings without quality loss. For semantic judgment, especially legal/tax/compliance relevance, source selection, topic taxonomy, research scope, and ambiguous intent, prefer model-led reasoning unless deterministic behavior has been proven better on representative cases. Use the project-local `deterministic-judgment` skill when making or reviewing these choices.

## Polars: streaming engine guidance

We no longer recommend using `streaming=True` in examples or new code. Prefer selective use of `engine="streaming"` on the few heavy `collect`/`sink_*` steps that are memory‑bound. Do **not** remove existing `engine="streaming"` calls wholesale; keep them where they provide memory headroom or speed.

**Defaults**
- For most queries, omit the engine argument and let Polars choose the default execution mode.
- Enable streaming explicitly only where it matters:
  ```python
  df = lf.collect(engine="streaming")
  ```

**Safe fallback wrapper**
Use a small helper so a streaming hiccup doesn’t break the pipeline:

```python
def collect_safe(lf, prefer_streaming=True):
    if not prefer_streaming:
        return lf.collect()
    try:
        return lf.collect(engine="streaming")
    except Exception:
        # optionally log a warning here
        return lf.collect()
```

Call `collect_safe(lf, prefer_streaming=True)` on large steps; flip the flag via config/env when needed.

**When to use streaming**

* Large scans + aggregations that risk high peak RAM.
* Long ETL chains writing to disk (`sink_*`) or handling datasets larger than memory.

**When not to force streaming**

* Small/interactive queries where simplicity matters more than peak‑RAM.
* Steps that rely on row order without making it explicit (add a `sort` if order is required).

**Migration note**

* Replace `collect(streaming=True)` with `collect(engine="streaming")` in samples.
* Keep selective `engine="streaming"` in the heavy paths; do not strip them globally.

## 3. Writing High‑Quality, Useful Tests

**Avoid external/infrastructure dependencies**

- Keep unit tests self‑contained. If a function depends on a database, network call, or file system, isolate those parts via dependency injection or monkeypatching so the test does not require the actual service. Using external dependencies slows down tests and makes them brittle[learn.microsoft.com](https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-best-practices#:~:text=Avoid infrastructure dependencies). Reserve integration tests for full system interactions.

**Follow clear naming conventions**

- Each test name should describe what it tests: include the method being tested, the scenario, and the expected outcome[learn.microsoft.com](https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-best-practices#:~:text=Follow test naming standards). For example, `test_calculate_tax_negative_price_raises_value_error()` conveys intent better than `test_calculate`.

**Use the Arrange–Act–Assert pattern**

- Structure tests into three clearly separated steps: **Arrange** your inputs (create objects and mock dependencies), **Act** by calling the function under test, and **Assert** on the result[learn.microsoft.com](https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-best-practices#:~:text=The ,consists of three main tasks). This improves readability and helps future maintainers understand what’s being tested.

**Keep tests minimal and focused**

- Provide the simplest possible input to verify the behaviour being tested[learn.microsoft.com](https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-best-practices#:~:text=Write minimally passing tests). Avoid unnecessary setup or extraneous data; this makes tests resilient to future refactoring.

**Avoid magic constants**

- Don’t hard‑code unexplained values in tests. If you need specific constants, assign them to clearly named variables or constants[learn.microsoft.com](https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-best-practices#:~:text=Avoid magic strings).

**Eliminate logic inside tests**

- Tests should verify behaviour, not compute results. Avoid conditionals or loops in the assertions; these introduce the risk of bugs in the tests themselves[learn.microsoft.com](https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-best-practices#:~:text=Avoid coding logic in unit,tests). If you need to verify multiple cases, use parametrization (e.g. `pytest.mark.parametrize`) to test several inputs with one function.

**Avoid shared state and use helper functions rather than global fixtures**

- Do not rely on test‑suite‑level `setup`/`teardown`; they often cause hidden coupling and make tests harder to read. Instead, use helper functions or fixtures to create the needed objects for each test[learn.microsoft.com](https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-best-practices#:~:text=If you require a similar,these attributes for several reasons).

**Keep a single Act per test**

- Each test should exercise one action. If you need to test multiple inputs or scenarios, parameterize the test instead of calling the function multiple times in one test[learn.microsoft.com](https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-best-practices#:~:text=When you write your tests%2C,Act task for each test). This makes failures easier to diagnose.

**Test public behaviour, not private methods**

- Private functions are implementation details. Verify behaviour through public APIs rather than testing private methods directly[learn.microsoft.com](https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-best-practices#:~:text=Validate private methods with public,methods). This ensures tests remain valid even when internal refactoring happens.

**Control time, randomness and other static references**

- When your code relies on functions like `datetime.now()`, wrap these calls behind interfaces or parameters so you can supply fixed values in tests[learn.microsoft.com](https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-best-practices#:~:text=Handle stub static references with,seams). This prevents flaky tests that depend on the environment.

**Polars DataFrame tests**

- When verifying Polars operations, use built‑in asserts such as `polars.testing.assert_frame_equal()` and `assert_series_equal()` to check equality[docs.pola.rs](https://docs.pola.rs/py-polars/html/reference/testing.html#:~:text=Asserts). For sorting or ordering issues, sort DataFrames before comparing or use the `check_row_order` argument. Create small, deterministic DataFrames within tests rather than relying on external data sources.

**Write meaningful assertions**

- Each test must have at least one assertion or an expected exception. Avoid `print()` statements or unconditional `pytest.skip()`. If a feature cannot be tested reliably because of external dependencies, mark it with a conditional skip and a brief explanation rather than leaving the test empty.

**Cover edge cases and error handling**

- For each function, design tests for normal scenarios, edge cases (e.g. empty inputs, negative numbers), and error conditions (invalid input types, missing keys). This improves coverage of untested branches and gives confidence in the robustness of the code.

## 4. Quick Quality Check

Run all quality gates with:

```bash
make check            # or: pre-commit run --all-files
```

This executes the full quality gate:

| Tool | What it does |
| --- | --- |
| **Black** | Formats code uniformly |
| **Isort** | Orders `import` statements |
| **Mypy** | Static type analysis |
| **Bandit** | Scans for common security issues |
| **Pytest + Coverage** | Runs tests; fails if coverage < 80 % |

> **Tip**: Install the pre-commit hook once with `pre-commit install`; then the checks run automatically on every `git commit`.

## 4. Commit Hygiene

- Use **Conventional Commits** (`feat:`, `fix:`, `docs:`, etc.).
- Don’t commit generated files, large data, or secrets—see `.gitignore`.

## 4.1 Deployment Hygiene

- Use git for server code deployment. Do not copy, rsync, or manually edit
  tracked production files in a server worktree unless the user explicitly
  approves an emergency exception.
- If an emergency exception is approved, tell the user immediately which files
  were changed outside git and restore the server to a clean git-managed state
  before considering the work complete.

## 5. Refactor Cycle

Every **4–6 weeks** we schedule a short “cleanup sprint” to eliminate duplicate code and improve readability (monitored via Sonar/GitClear reports).

## 6. Green Before Merge

A pull request may be merged only when all required CI checks show **green**:

1. Tests pass and coverage stays ≥ 80 %.
2. Black, Isort, and Mypy return no errors.
3. Bandit reports no medium- or high-severity issues.

## Appendix · Starter Configs

```yaml
check:
  black .
  isort .
  pytest --cov=src --cov-report=term-missing --cov-fail-under=80
  mypy src/
  bandit -r src/
repos:
  - repo: https://github.com/psf/black
    rev: stable
    hooks: [{id: black}]
  - repo: https://github.com/pycqa/isort
    rev: stable
    hooks: [{id: isort}]
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1
    hooks: [{id: mypy}]
  - repo: https://github.com/PyCQA/bandit
    rev: v1
    hooks: [{id: bandit}]
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: pip install -r dev-requirements.txt    # pytest, coverage, etc.
      - run: make check
```

## 7. LLM Wrapper Integration

To standardise LLM calls throughout the project:

- **Initialise once** using `modules.llm.llm_call_wrapper.init_llm_wrapper` and store the resulting `llm_wrapper` in your session context.
- **Pass `llm_wrapper` through every logic layer** so lower‑level functions can make recorded or replayable LLM calls.
- Use `modules.llm.model_router.query_llm_return_json` or `query_llm_return_text` to send prompts. Both support OpenAI-style tool calling via the `tools` and `tool_choice` arguments.
- Each `query_step` is mapped to a provider, model, and batch capability via `modules.utilities.config.select_provider`.

### Example flow from UI to logic

```python
from modules.llm.llm_call_wrapper import init_llm_wrapper
from modules.check_entries.logic import check_entry_against_text
from modules.utilities.session_context import SessionContext

session = SessionContext.from_state({})
init_llm_wrapper("", session=session)
llm_wrapper = session.state["llm_wrapper"]

result = check_entry_against_text(
    llm_wrapper,
    entry,
    pdf_text,
    "eng",
    tools=my_tools,
    tool_choice="required",
)
```

Inside `check_entry_against_text`, the logic layer calls `query_llm_return_json`, which uses `select_provider(query_step)` to resolve the actual provider/model and determine whether batching is supported.

## Design Context

### Users

The primary homepage visitor is a professional who is curious about applying
Codex to serious work. The homepage must explain the Mparanza point of view,
make the Codex harness concrete, and show whether Vera or Clara fits the
visitor's profession. Inside product surfaces, users arrive with a focused task
and need a calm, reliable, reviewable workflow rather than novelty or broad
exploration.

### Brand Personality

Elegant, professional, restrained. The desired emotional result is confidence,
calm, and agency. Mparanza should feel edited and considered rather than salesy,
playful, ornamental, or like a generic AI startup.

Mparanza is Vera and Clara together. They are the complete product pair, not
unrelated products inside a visually separate parent brand. Vera and Clara
share one blue visual identity.

### Aesthetic Direction

Default to light mode and a clean white canvas. Favor strong live typography,
generous whitespace, thin rules, disciplined spacing, and restrained neutrals.
Use `Instrument Sans` throughout the Mparanza website and workflow UI,
including form controls. Preserve monospace only where code or structured data
requires it. Presentations and generated reports may follow their own
output-specific typography. Create hierarchy through deliberate weight, scale,
spacing, and color rather than substituting unrelated typefaces.

The homepage should feel like a continuous editorial argument, not a SaaS
landing page, dashboard, or plugin marketplace. Detailed Vera and Clara pages,
including pages that explain their functions, must confidently use their shared
navy/blue/cyan identity. The homepage may use blue more selectively, but it must
make the connection to Vera and Clara perceptible rather than implying that
Mparanza is an unrelated black-only brand.

Avoid gimmicky gradients, glossy cards, decorative shadows, noisy pills,
overloaded status chips, generic AI motifs, tinted homepage backgrounds, and
unnecessary decoration.

### Design Principles

1. Present Mparanza as Vera and Clara together, with blue as their shared
   identity and black/neutral typography providing editorial hierarchy.
2. Use the shared blue system consistently on all detailed Vera and Clara
   product and function pages.
3. Preserve the homepage's quieter editorial character while using blue as a
   meaningful identity signal, not generic decoration.
4. Lead with professional work, specialist method, and useful output before
   technical package mechanics.
5. Prefer concrete proof, typography, spacing, and alignment over broad claims
   or decorative emphasis.
6. Make every word and visual signal earn its place; interfaces should feel
   stable, intentional, and professionally trustworthy.

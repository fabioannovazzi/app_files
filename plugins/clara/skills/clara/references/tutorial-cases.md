# Worked examples for Clara

Choose 3–4 distinct current workflows for the user's work. The packaged starters
are fictional inputs, never precomputed answers. Read the selected skill in full.
Do not replace an unavailable capability with a mock to finish the introduction.

| Starter | Workflow | Natural request and actual execution |
| --- | --- | --- |
| `actual-budget.xlsx` | `reporting-engine` | “Mi mostri dove siamo rispetto al budget?” Inspect, review the recipe, then run the real budget helper; explain amount and percentage and do not invent causes. |
| `advisory-brief.md` | `html-deck` | “Trasformiamo questi risultati in una presentazione?” Author the actual deck from this evidence, then render and inspect it with the normal specialist QA. |
| The actual deck produced above | `deck-correction` | “Proviamo a cambiare questa slide insieme?” Use a separate copy, bind the user's actual feedback to the deck, execute and verify the real correction contract. |

In the bound native working chat, prepare selected inputs:

```text
python3 <clara-root>/scripts/local_onboarding_case.py --thread-id <actual-worker-id> --workflow <selected-workflow> --token <current-token> --phase demo --source <selected-absolute-file>
```

Use `--session <id>` for later lessons and repeat `--source` for multiple files.
For the user's practice, use their actual requested change in a fresh source copy
and `--phase practice` after the demonstrated result has been recorded.
The helper verifies the live handoff and creates a separate attempt below the
local tutorial marker. Clara receives a project with immutable source copies,
hashes and an output directory; its specialist owns the advisory contract and
execution. Lucia receives a real private portable Studio Archive context and run,
without configuring the production archive. Follow each specialist's real intake,
review and completion contract; do not pretend that preparation completes it.
Reuse the saved `tutorial_case.json` after interruption instead of duplicating work.

Inspect actual outputs and record their paths as demonstration or practice evidence.
The model evaluates the meaning; the helper only checks identity, paths and state.
A reviewed draft may be the teaching objective. Never fabricate professional review
or the user's participation. Do not publish, send, call hosted interview services,
request stamps or transmit tutorial data. The compatibility marker is understood
by existing shared receipt clients; it does not merge this product's profile with Vera.

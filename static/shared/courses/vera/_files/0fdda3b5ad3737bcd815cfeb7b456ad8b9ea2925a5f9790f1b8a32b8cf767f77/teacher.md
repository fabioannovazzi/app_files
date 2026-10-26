# Track evidence and decisions in an ESG case

The explanation and a short practice take about 5–8 minutes. Processing and your questions can extend the session.

Speak with the teacher using the standard Codex voice. In the working chat, open in the window beside it, the function runs the case using the prepared files and shows its actual results. The teacher follows those results: interrupt, ask questions and change the pace whenever you need.

Start from the prepared material and teach the complete first use. Select 3–4 relevant functions during onboarding; on later visits start with what the user wants to do today. Adapt pace and explanations. Create custom examples when helpful, using the same workflow and checking new inputs. Read execution-request.json, use the real paired local case, and connect explanations to verified working-chat results. Never invent results, user answers or understanding confirmations. Opening the kit does not complete the lesson.

## 1. When to use it · 45 s

Connect the function to a concrete professional task.

Learn to trace a value to its source, prepare a partial draft and identify what needs review after an update.

Entirely fictional: Officina Selce, one site and declared 2026 electricity use. The initial value is 0 kWh; a correction states 15 kWh. No certified measurement.

ESG evidence foundation in desktop Codex and local Work where supported. In Cowork the course uses one written conversation. No complete ESG report, VSME/ESRS or taxonomy calculation, assurance opinion, signing or sending.

## 2. Files and request · 60 s

Open the files in the working window and show how to request the result.

Read brief-en.md and energy.csv. The first numeric cell is zero; the blank 2025 cell is not available. The excluded site is declared not applicable for this fictional case only; a blank alone does not establish that. Keep energy-update.csv for the next step.

Vera, prepare the fictional 2026 Officina Selce case. Bind values to files, distinguish zero, missing and not applicable, show a decision for review and a partial draft. Then import the correction from 0 to 15 kWh and show what became outdated.

## 3. Run the workflow · 105 s

Explain the step happening now and wait for its actual result.

Use Studio Archive to prepare a separate tutorial client, import the brief and energy.csv and start the current workflow. Agree period, service preparation and reporting basis unresolved without automatically selecting a standard. Start a synthetic case and bind rows 1, 2 and 3 of column kwh.

Show the original, locator, interpreted value and rationale. Before record_decision ask for the participant’s actual decision on these exact versions and dependencies. Leave it open if none is given. Label any simulation; never attribute it to the participant. Build a partial_draft memo with exact dependencies and no compliance claim.

Preserve the first run. Import energy-update.csv as a new immutable source and start a successor in the same engagement selecting old and new inputs. start_case uses the first previous_context; bind_evidence keeps logical ID energy and records 15. Open resume_case: energy v1 and dependent decision/draft are outdated, energy v2 is current; missing and not applicable remain distinct.

During the lesson, the working chat runs the function and produces the result. If a step is unavailable, explain what is missing and keep the lesson incomplete.

## 4. Use the result · 75 s

Open the document just produced and show where to start reading.

esg_state.json with files, hashes, cells, versions, rationales, decisions and dependencies; partial Markdown and JSON drafts.

Both Studio Archive contexts, originals and history, codex_run_review.md and the readable report of actual model reads. These are outputs to execute now, not supplied results.

Check client, period, unit, scope and source. Declared zero does not prove actual zero consumption. Missing needs collection; not applicable needs a reason. Review interpretation and sufficiency. A correction invalidates dependent decisions without renewing them. A declared name is not an authenticated signature.

## 5. Pause and check · 45 s

Make these checks at the indicated points during the work.

Before deciding, locate all three cells and explain why the two blanks have different statuses.

After updating, show the current version and preserved old decision/draft; identify what needs review.

These pauses help you learn how to use the function. They are not a technical detail quiz.

## 6. Try it yourself · 60 s

Let the user formulate the request and guide their attempt.

With less guidance, use files/practice/ in a fresh tutorial client: Laboratorio Quarzo declares 8 kWh, then 12. Request the case, distinguish both blanks, prepare the initial draft and import the correction in the same engagement. Preserve the demo. Give your own decision or leave it open.

Find 0 then 15 kWh in the demo and 8 then 12 in practice. Original files and history remain readable; dependent decision/draft need review. The two null values retain distinct statuses and no complete report or opinion is approved.

Repeat by selecting client, engagement, period and relevant CSV/text files; state the request and review sources and interpretations. Updates are new inputs in the same engagement. The short guide targets 5–8 minutes; processing and practice may extend it. Files and progress stay local; model reads enter its context without automatic anonymisation.

The kit contains fictional files and a prepared outline. Demonstration and practice results come from fresh runs of the current function.

The lesson library, profile and progress stay on your computer. They are not sent to Mparanza. Voice and content read in chat are processed by your OpenAI account: local storage does not mean offline inference.

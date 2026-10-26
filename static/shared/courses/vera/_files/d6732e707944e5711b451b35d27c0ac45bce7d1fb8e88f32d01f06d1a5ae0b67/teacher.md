# Reconcile a bank statement with Vera

The explanation and a short practice take about 5–8 minutes. Processing and your questions can extend the session.

Speak with the teacher using the standard Codex voice. In the working chat, open in the window beside it, the function runs the case using the prepared files and shows its actual results. The teacher follows those results: interrupt, ask questions and change the pace whenever you need.

Start from the prepared material and teach the complete first use. Select 3–4 relevant functions during onboarding; on later visits start with what the user wants to do today. Adapt pace and explanations. Create custom examples when helpful, using the same workflow and checking new inputs. Read execution-request.json, use the real paired local case, and connect explanations to verified working-chat results. Never invent results, user answers or understanding confirmations. Opening the kit does not complete the lesson.

## 1. When to use it · 45 s

Connect the function to a concrete professional task.

Learn to compare bank movements with the bank ledger and use the reconciliation for a month-end review.

Officina Arco is closing March. Its bank statement and bank ledger should describe the same payments. We will compare them and inspect the resulting workpapers.

One EUR bank account, March 2026. The case uses exact transaction references and individual payments. Other accounts and periods are outside this run.

## 2. Files and request · 60 s

Open the files in the working window and show how to request the result.

Open bank-march.csv, bank-ledger-march.csv and case-en.md. The statement is the external movement source; the ledger is the accounting comparison. Dates are ISO dates and outgoing payments are negative in both exports.

Vera, reconcile Arco’s March bank statement with its bank ledger. Show the matched payments, any unmatched movements and the checks I should review.

## 3. Run the workflow · 105 s

Explain the step happening now and wait for its actual result.

Vera imports both exports into the teaching case and inspects their structure. Confirm the account, dates, amount signs and transaction-reference columns.

Review the proposed matching rules in ordinary accounting terms: individual payments, exact references and amounts, with no reuse of a movement. The current pipeline performs the comparison locally.

Open the generated workbook and review notes. Follow one matched bank payment to its ledger reference, then locate the unmatched-movement lists and control results.

During the lesson, the working chat runs the function and produces the result. If a step is unavailable, explain what is missing and keep the lesson incomplete.

## 4. Use the result · 75 s

Open the document just produced and show where to start reading.

Reconciliation workbook and detailed tables: use these to inspect matched payments and any remaining movements.

Review notes and controls: explain coverage, matching rules and issues requiring further evidence.

Check that both files cover the same account and period. Trace one match to both source rows. A reconciled bank movement does not itself establish the tax treatment of the underlying invoice.

## 5. Pause and check · 45 s

Make these checks at the indicated points during the work.

Before running, identify which file comes from the bank and which from accounting.

At delivery, find a matched payment and where an unmatched item would appear.

These pauses help you learn how to use the function. They are not a technical detail quiz.

## 6. Try it yourself · 60 s

Let the user formulate the request and guide their attempt.

Use bank-april.csv and bank-ledger-april.csv to request a fresh reconciliation through 4 April. These cumulative files add the third invoice payment; retain the March result.

The new run includes the April movement. Explain how you would investigate a bank movement missing from the ledger.

Supply comparable bank and ledger exports, name the account and period, review the proposed interpretation and use the resulting reconciliation to resolve differences.

The kit contains fictional files and a prepared outline. Demonstration and practice results come from fresh runs of the current function.

The lesson library, profile and progress stay on your computer. They are not sent to Mparanza. Voice and content read in chat are processed by your OpenAI account: local storage does not mean offline inference.

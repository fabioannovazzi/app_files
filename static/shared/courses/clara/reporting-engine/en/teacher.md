# Before the chart, establish what the data means

A guided walkthrough of about 6½ minutes. Voice setup, external processing and optional practice are outside the lesson time.

Talk with the teacher using the standard Codex voice. In the second chat, open beside it, inspect the files and result. The chats stay paired; interrupt, ask why or slow down whenever you need.

Use this prepared material. Do not rewrite the lesson or invent results. Speak in short turns, allow inspection time and listen to actual answers. Do not reveal the solution before the attempt. Timings include observation and conversation, not just spoken text. Showing these files does not complete demo, practice or understanding records. The teacher judges relevance using only its own product's catalog.

## 1. Your objective · 45 s

Listen to the request. Connect this case to work you already do.

The fictional dataset reports net sales of EUR 40,000 in January and EUR 50,000 in February. There is no separate Discount field. Source notes confirm that Sales already includes discounts, so subtracting them again would be wrong.

Clara, show the sales trend and explain which data you are using.

## 2. The starting evidence · 60 s

Look at the documents in the other chat. Find one useful fact and one missing item.

R1 has two months; R2 defines Sales as net. Discount is absent as a separate measure, not a recorded zero.

[["2026-01", "EUR 40,000", "Net sales"], ["2026-02", "EUR 50,000", "Net sales"], ["Separate Discount", "Absent", "Already reflected in Sales"]]

## 3. How the workflow works · 75 s

Follow the three steps. Pause at the decision that changes the result.

Run dataset intake and inspect data, profile and notes. Review metric meaning, aggregation and Sales, Discount and COGS roles; headers alone are insufficient.
Select a compatible capability and render through Clara's adapter, preserving the effective request and output proof.
Open the result and verify values, units, periods and conclusion. Reuse a compatible stable semantic contract on subsequent uploads rather than recreating meaning every time.

## 4. Read the result · 90 s

Open the example in the second chat. Connect each conclusion to its source.

Net sales move from EUR 40,000 to EUR 50,000, a EUR 10,000 or 25% increase. Separate discounts and costs are unavailable.

[["January", "EUR 40,000", "R1 · net sales"], ["February", "EUR 50,000", "R1 · net sales"], ["Change", "+EUR 10,000 · +25%", "January base EUR 40,000"]]

## 5. The check that matters · 75 s

Before revealing the answer, say what you would check.

Technical compatibility and semantic correctness are different checks. Valid columns can still have a wrong business mapping.

With no Discount column, can we state that no discounts were granted?

Compare your reasoning: No. Sales is net and no separate discount measure is supplied. Column absence does not establish absence of discounts.

## 6. Try it together · 45 s

Choose whether to try now or keep the example for your next assignment.

Add March under the same Sales definition, then verify contract reuse and the refreshed chart.

Select CSV, Excel or Parquet with metric notes. Actual/Budget reports use Clara's own budget route within this workflow.

This is a prepared teaching example, not a receipt for a new execution. Sources and decisions are fictional; no professional approval is implied. For your own files, the current workflow performs its checks and preserves the actual outputs.

The lesson library, profile and progress stay on your computer. They are not sent to Mparanza. Voice and content read in chat are processed by your OpenAI account: local storage does not mean offline inference.

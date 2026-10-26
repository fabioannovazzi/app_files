# Extract tax data from documents with Vera

The explanation and a short practice take about 5–8 minutes. Processing and your questions can extend the session.

Speak with the teacher using the standard Codex voice. In the working chat, open in the window beside it, the function runs the case using the prepared files and shows its actual results. The teacher follows those results: interrupt, ask questions and change the pace whenever you need.

Start from the prepared material and teach the complete first use. Select 3–4 relevant functions during onboarding; on later visits start with what the user wants to do today. Adapt pace and explanations. Create custom examples when helpful, using the same workflow and checking new inputs. Read execution-request.json, use the real paired local case, and connect explanations to verified working-chat results. Never invent results, user answers or understanding confirmations. Opening the kit does not complete the lesson.

## 1. When to use it · 45 s

Connect the function to a concrete professional task.

Learn to turn readable tax documents into a field list that you can verify against its sources.

The practice is preparing Marco Prova’s data. It has a fictional Italian CU income certificate and F24 payment form and wants to read their values without manually retyping them.

Italian source documents, explained in the chosen language. Extracted values describe the documents; they are not a tax return or a tax calculation.

## 2. Files and request · 60 s

Open the files in the working window and show how to request the result.

Open CU-income.md and F24-first.md. These are readable teaching transcriptions with invented income, withholding and payment fields. Specify the 2026 filing campaign and distinguish document year from tax period.

Vera, extract the tax data from Marco Prova’s documents for the 2026 filing campaign. Show the fields, each value’s source and what I need to check.

## 3. Run the workflow · 105 s

Explain the step happening now and wait for its actual result.

Vera imports the documents into the teaching case and runs current preparation and extraction. Follow which files it can read and how their document types are identified.

The workflow produces structured fields and a summary. If a document type is uncertain, Vera checks its content and records its interpretation through the normal review process.

Open the new summary and CSV. Find income and withholding in the CU, then year, code and amount in the F24, tracing them back to the source text.

During the lesson, the working chat runs the function and produces the result. If a step is unavailable, explain what is missing and keep the lesson incomplete.

## 4. Use the result · 75 s

Open the document just produced and show where to start reading.

Tax-data summary: groups fields by document and states limitations.

Field CSV and extraction report: let you check values, sources and documents that were not processed.

Compare values with both sources, including year and currency. Also inspect documents with no extracted fields: an empty result does not establish that the document contains no useful information.

## 5. Pause and check · 45 s

Make these checks at the indicated points during the work.

Before starting, identify the two documents and filing campaign.

At delivery, trace one extracted value to its source and find any extraction limitations.

These pauses help you learn how to use the function. They are not a technical detail quiz.

## 6. Try it yourself · 60 s

Let the user formulate the request and guide their attempt.

Add F24-second.md to the two initial documents and request a fresh extraction. The second F24 is additional; retain the preceding result and original document.

The new list distinguishes both F24 documents and their sources. You can find the year and amount before reusing a value.

Supply readable documents, specify country and filing campaign, request extraction and verify fields against their sources before professional use.

The kit contains fictional files and a prepared outline. Demonstration and practice results come from fresh runs of the current function.

The lesson library, profile and progress stay on your computer. They are not sent to Mparanza. Voice and content read in chat are processed by your OpenAI account: local storage does not mean offline inference.

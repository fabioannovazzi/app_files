# Intelligent assetti: implementation and validation, 7 September 2026

## Delivered scope

Assessment and subsequent review use the selected Codex/Cowork model to interpret
company evidence, choose targeted questions, connect processes and risks to actual
controls, reconstruct information timing and draft a management discussion brief.
A separate factual challenge checks the draft against original evidence before
saving. The standard-library helper validates links, preserves the full analysis
and renders it in the memo. It does not decide adequacy or invoke another model.

The new `intelligent_review` extension is required by the skill for new runs.
Historical v1 records remain usable for follow-up. Coverage, process evidence,
questions, chronology, decisions to discuss and next-review evidence are visible
in the memo. Changes to the analysis invalidate approval of an earlier digest.

The public page calls this **Adeguati assetti: valutazione intelligente** and
explains those operations in Italian, English, French, German and Spanish. The
catalog retains the existing capability name, Adeguati assetti. No certification,
turnkey initial design or unattended operating monitoring is advertised.

## Live reasoning trial: evidence and limits

Eight synthetic narratives were submitted through the repository LLM wrapper and
model router to the configured `gpt-5.4-mini` model. No client data was used and no
legal research was requested. The first pass used the method reference; subsequent
passes included the skill and revised method. The final trial used a draft followed
by a separate model-led factual challenge against the original case. These are
short reasoning probes, not full Codex or Cowork client runs and not an independent
professional evaluation. Repeating a case after editing the instructions is a
development check, not a held-out benchmark.

| Case facts | Observed behavior and remaining limitation |
| --- | --- |
| Owner-managed shop, two employees; six weekly collection reviews and follow-up evidenced, no written procedure or rest-of-year evidence | Recognized the informal control and limited the conclusion to the sample. Still proposed a one-page procedure without a sufficiently specific unmet need. Professional review must challenge unnecessary paperwork. |
| Detailed monthly policy; six reports four months late, management decisions precede receipt | Identified observed lateness/non-use and asked about alternative timely information. Appropriately moved beyond merely noting a missing document. |
| Director says weekly credit reviews operate; clerk says they stopped in May; ledger has overdue balances without review annotations | Preserved the disagreement and requested a dated operating example. Some language still overstated what a director's statement establishes; attribution needs review. |
| April assessment; March-dated procedure uploaded September, first circulation email July | Did not treat upload/document date as proof of April operation. Still suggested an April-or-May example; May alone cannot establish April operation. |
| Annual bookkeeping engagement; invoices delivered at year end; owner assumes monthly cash monitoring; weekly bank checks but no receivables/payables schedule | Detected the mandate/handoff gap and proposed a useful schedule and information flow. Earlier draft invented company size and assigned extra work to the provider; factual challenge removed the size assumption and avoided assigning preparation unilaterally. Proposed timing still needs agreement. |
| Worker cooperative, director reports no prestito sociale, member labor records supplied, cooperative review report unavailable | Final trial preserved the reported status and treated missing review evidence as a limitation. Initial ambiguous English wording was mistranslated as loans to members; the method now distinguishes funding collected from members. No legal applicability was verified. |
| Bank statements only; user describes the year as profitable and asks about all arrangements | Withheld a company-wide adequacy conclusion and requested operating evidence. Still described historical economic outcome too loosely; bank movements alone cannot substantiate profit. |
| Prior action requires weekly credit review and follow-through; policy signed yesterday, no operating cycle; user asks to close as working | Kept the operating action open and requested the first complete cycle. A drafting task could separately be complete; operation cannot be inferred from the signature. |

The trial supports proceeding with a professional-reviewed assessment workflow.
It does **not** establish reliable unattended judgment or universal model quality.
The most material unresolved model weaknesses concern unnecessary formalization,
period-specific evidence and careful distinction between statements and facts.
The workflow's factual challenge reduces some errors but is not an independent
review and did not eliminate every error in this small model trial. The selected
host model may differ; model capability materially affects the result.

Before claiming field effectiveness, run the agreed supervised company pilot and
measure source corrections, professional overrides, unanswered questions, utility
of proposed actions and evidence from an actual subsequent operating cycle. Do
not advertise a half-day delivery time, a fee or a certification from this trial.

## Software verification

Tests exercise linked process/question/chronology evidence, excluded scope,
save/reopen fidelity, rejected unknown references, incomplete records and invalidated
professional approval after changing the analysis. Packaged execution uses real
portable archive contexts in Codex, ChatGPT-upload and Claude ZIPs and verifies
that the new reasoning appears in the memo, not only in stored JSON.

Source review and provenance are retained in:
- `vera-assetti-source-review.md` (provided documents and public source analysis);
- `vera-assetti-francesco-2026-09-07.md` (attributed machine transcript);
- `vera-assetti-delivery-plan.md` (assessment scope and supervised initial-design pilot).

The research documents are product documentation; they do not turn those sources
into a frozen legal checklist. The runtime must verify applicable law and current
professional sources for each actual entity and review period.

# Shared legal-opinion data review

Lucia uses `modules/deep-research-validator` and `modules/prompt-optimizer`,
resolved to their sibling source components in the repository. The canonical
source-bound data records are maintained in Vera's `privacy/workstreams/`
register for those two shared implementations. Lucia's adapters are
`skills/quesito-legale-fiscale/SKILL.md`, `skills/adversarial-opinion/SKILL.md`
and `skills/prompt-optimizer/SKILL.md`; they add no helper implementation or
external transfer. They retain the lawyer's governing-law, source and final
professional decisions and the existing Lucia runtime boundary.

The optional installed Deep Research route receives the prepared brief,
contract, selected case material and source list in the current host context.
Its availability and selection are checked before use. The separate manual
ChatGPT handoff remains an expressly chosen destination. Informational research
ends after ordinary validation. For an opposing examination, the selected
model may read the complete reviewed original, material case facts, source
captures, complete opposing result and comparison. Public source queries can
contain case facts needed for research. There is no automatic anonymization
or claim that model-read material remains local-only.

Both opinions use the same existing Studio Archive validation run, with
preparation in its separate run. The shared helper enforces exact phase paths,
file hashes and declared review states; legal support and opposing-case judgment
remain model-led and subject to the lawyer's review. Without local tools Lucia
continues in chat and states the missing durable artifacts. The shared public
question, planner and opposing-opinion pages describe these same paths.

Packaging tests compare the complete shared component bytes in Vera and Lucia
for Codex, ChatGPT upload and Cowork, and execute sealed-run verification from
all six packages. Product-specific code or a new recipient requires a new
review; this record is not a legal compliance certification.

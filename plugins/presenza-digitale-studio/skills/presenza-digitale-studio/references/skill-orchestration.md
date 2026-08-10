# Skill orchestration

Use the narrowest available host skill for each contribution. Read a selected
skill completely before using it. Record selected and unavailable skills in
the Artifact Card.

| Stage | Preferred skill | Purpose |
| --- | --- | --- |
| Initial design context | `teach-impeccable` | Establish reusable studio design context once when no approved profile exists. |
| Existing-site diagnosis | `critique` | Assess hierarchy, information architecture and UX effectiveness. |
| Copy | `clarify` | Improve headings, labels, calls to action and supporting copy without changing verified meaning. |
| Typography | `typeset` | Establish readable, disciplined type hierarchy. |
| Layout | `arrange` | Improve spacing, alignment, composition and visual rhythm. |
| Responsive design | `adapt` | Make the implementation work at desktop and phone widths. |
| Implementation | `frontend-design` | Build the working responsive site from the accepted brief. |
| Identity consistency | `normalize` | Align the result with an approved studio profile when one exists. |
| Final detail | `polish` | Correct alignment, spacing and visual inconsistencies. |
| Quality review | `audit` | Review accessibility, resilience, performance and interface quality. |
| Optional imagery | `imagegen` | Create or edit a visual only when the studio selects that route and the result is reviewed. |
| Optional art direction | `creative-production:produce` | Explore non-final art directions; never supply claims, copy or publication approval. |
| Optional hosted build | `sites:sites-building` | Build the run-owned adapter in `work/sites-project/` only when the selected route provider is `sites`; Vera browser QA remains mandatory. |
| Optional Sites publication | `sites:sites-hosting` | Save and deploy the bound Sites archive after the Vera package and review chain are current; always follow a Sites build and `sites-handoff.md`. |

Do not require every skill. Skip irrelevant stages and state unavailable
optional capabilities. When no design skill is callable, apply
`website-quality-standard.md` directly and disclose that the specialized skill
pass did not run.

For another hosting platform, prefer its installed connector or supported
browser workflow. Keep hosting credentials outside Vera and stop at security or
account ambiguity. A platform-specific publish action is never implied by the
request to design the site.

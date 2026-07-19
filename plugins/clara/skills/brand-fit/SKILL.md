---
name: brand-fit
description: Use when a user wants Clara to compare completed retailer signals with a brand's current presence at that retailer and the brand's owned catalogue, create a private local HTML Brand Fit report, or ask whether that report is correct.
---

# Brand Fit

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../clara/SKILL.md`.

Resolve `../../modules/attribute-reporting` from this skill directory when it
exists; otherwise resolve `../../../attribute-reporting` in the repository.
Read that component's `skills/brand-fit/SKILL.md` completely and follow it.
Treat the resolved component root as a read-only execution root for its scripts,
requirements, references, and vendored modules. Run component helpers with that
root as the working directory, but create every user run and artifact outside
the resolved component root, every Git repository, and every plugin cache.
Never place run artifacts in the packaged component.

Before running component helper scripts, delegate the dependency check from
the Clara root:

```bash
python scripts/check_dependencies.py --module attribute-reporting
```

Brand Fit is distinct from Retailer Signals. Start only from a completed,
checked Retailer Signals analysis, then compare its signals with both the
brand's current presence at the selected retailer and the brand-owned catalogue
in the stored database snapshot. Do not describe that snapshot as a live shelf
check. The local Retailer Signals report is not uploaded to the server.

Codex owns semantic interpretation, report authorship, and independent review.
The server and user need no model-provider API key. Product images and the HTML
report remain local unless the user explicitly asks to share a finished output.
Do not register the report in an advisory case, convert it to a presentation, or
publish it unless the user separately asks for that follow-on work.

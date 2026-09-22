---
name: vera-contributors
description: "Prepare or review Vera contributor cards using verified LinkedIn profiles, exact profile-photo bindings, and optional website links."
---

# Vera Contributors

Use this skill when adding, updating, or reviewing a card in Vera’s Contributors section.

## Card contract

“Contributors” is the section title, not a card label. Each card may contain:

1. The exact person’s LinkedIn profile photo, stored as the direct image URL observed on that profile.
2. Full name.
3. Professional profile and location.
4. A contribution description, either person-specific or a shared approved description that accurately explains the contributor's role.
5. The person’s public LinkedIn profile link.
6. Optional public website, only when it is verified and bound to the exact person.

Do not remove an approved contribution description merely because it is shared across cards: a common line such as “Aiuta Vera con: test, feedback e casi d’uso professionali” explains the relationship and must remain visible when it is the agreed description. “Contributore di Vera” alone is too vague. Do not invent a biography, profession, location, contribution, or website. If a contribution is not supported, mark it as pending or ask for the missing approved content. If no verified website exists, omit the website field entirely; never render a placeholder.

## LinkedIn sourcing

For the professional profile, open the exact LinkedIn URL supplied for the person and read the person’s own headline or current professional descriptor. Normalize it into concise Italian only when this preserves the stated profession and location. Do not infer a title, employer, seniority, or specialization from the name, photo, search results, or a different profile.

For the photo, inspect the exact profile page and bind the direct `media.licdn.com` image URL to that same person’s card. Do not choose an image by search-result order, array position, generic alt text, or visual similarity alone. Keep the direct LinkedIn image URL in the card so a later LinkedIn image change can be reflected by updating that URL. Verify the URL, name, profile descriptor, and photo binding together before publication.

Keep the contribution description distinct from the professional profile. A shared approved contribution description may be reused verbatim for multiple contributors; do not delete it just because it is repeated.

When the user asks for proposed alternatives before contributor approval, draft distinct area-based options rather than paraphrases, keep each under the requested length, and treat them as proposals rather than verified biographical facts. Apply them to cards only when the user explicitly requests publication.

## Website sourcing

The website field is optional. Add it only when a public website is supplied or verified for the exact contributor. Verify that it resolves publicly and identifies the named contributor before publication. Keep it as a separate, clearly labelled link from LinkedIn. If no verified website exists, omit the field entirely; never add a placeholder or “pending” website entry.

Sort cards by surname. When a LinkedIn field is unavailable, leave it explicitly pending or omit it; never publish invented content. Verify the rendered order and the exact person-to-photo, name-to-profile, contribution, LinkedIn, and website bindings before publication.

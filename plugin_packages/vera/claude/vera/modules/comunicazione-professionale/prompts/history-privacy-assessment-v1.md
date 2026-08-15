# Professional communication history privacy assessment v1

Act as an independent privacy reviewer in a fresh host session. Read only
`history_privacy_assessment_packet.json` and the pseudonymized derivative paths
it lists. Do not open the original history snapshots, mechanically stripped
intermediates, pseudonymization result, identity map, generation packet, or any
later workflow artifact.

Review every derivative for contextual identifiers that would make a person,
organization, address, location, role, client, or case identifiable. Look for
names left in prose, rare roles, precise addresses, and combinations of dates,
amounts, places, industries, procedural facts, or relationships that remain
identifying together. Preserve complete prose and structure: ordinary dates,
amounts, headings, salutations, signatures, and formatting signals are not a
privacy defect unless their context identifies a person or case.

Return JSON matching `history_privacy_assessment.schema.json`. Cover every
document once and in the listed order. Do not quote or repeat a suspected
identity. Locate a finding only by document ID and one-based paragraph number,
classify it, and explain the required generalization without reproducing the
private text. Use `ready` only when no material contextual identity remains.
Do not assess technical accuracy, editorial value, voice quality, or whether a
new communication should be published.

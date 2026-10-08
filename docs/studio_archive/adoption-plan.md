# Studio Archive adoption implementation

## Evidence and intended behaviour

A fresh archive session reports no configuration even when another session has
registered the client. Reconfiguration restores the portable ledger but loses
private legal-name lookup. Fix discovery and private identity continuity without
sharing active session configuration, run selection, search databases or credentials.

## Plan

1. Retain the last explicitly approved archive root in an owner-private profile.
   Revalidate access before adopting it into a fresh isolated session. Existing
   sessions remain pinned. Explicit state directories remain isolated unless an
   explicit profile directory is supplied. Do not scan old sessions or infer roots.
2. Store root-specific confirmed identity aliases in that private profile. Serialize
   identity transactions, keep values out of safe directory results, and retain
   client manifests as durable identity authority. Migrate only the current session's
   valid registry after an approved configuration; never overwrite conflicting IDs.
3. Distinguish connection, registration and engagement selection in instructions.
   Reuse established choices and consolidate the client/source/write confirmation.
4. Add a separate, explicitly selected standalone task context for invoice XML,
   prompt preparation and legal-answer validation. Keep source receipts and exact
   output containment, with no fictional client, client registration, archive setup
   or silent later adoption. Preserve specialist interpretation and export approval.
   Other accounting/operational engines retain their client ledger requirements.
5. Test fresh processes, root changes, concurrent identity updates, invalid profile
   state, source changes, unbound files and output escape. Run the packaged file
   routes and Linux/macOS/Windows CI. Native host and Francesco's Windows acceptance
   are separate from automated and synthetic tests.
6. Refresh privacy evidence, rebuild affected host distributions, verify parity,
   merge only with required CI green, deploy through git, verify public ZIP hashes,
   post a bounded release update to #studio-archive, and clean up this task's branch
   and worktree. Marketplace remains untouched.

## Judgment boundary

Fixed checks protect exact paths, bytes, receipt closure and concurrency. Choosing
standalone versus client work, professional relevance, client ambiguity and legal
or tax conclusions remain model/user decisions, never keyword classifiers.

## Implemented release and acceptance boundary

Vera 0.1.353 implements approved-root recovery, root-specific private aliases and
locked identity transactions. Standalone source-bound task contexts support invoice
XML, legal-question preparation and answer validation. Instruction changes prefer
a focused deliverable for clearly isolated work and reuse confirmed archive choices
for recurring work. Clara 0.1.255 and Lucia 0.1.88 carry aligned shared dependencies.

Fresh-process, concurrent-registration, source-containment, invoice-export and
packaged Cowork regressions pass locally. All host packages are rebuilt from source;
privacy manifests and course provenance are refreshed. The CI matrix adds explicit
Linux, macOS and Windows recovery checks. This evidence does not establish Francesco's
installed Windows version or the model's actual conversational routing there, and
there is no measured adoption uplift. His acceptance case remains: review an existing
client contract in a new chat without archive setup or duplicate registration, then
create one standalone invoice without archive setup while retaining export approval.

## Existing-session upgrade correction

The coordinated 0.1.354 candidate contains the adoption implementation. A further real upgrade probe found that enabling the durable profile for an already-approved legacy session could create its parent with mode 0755 before identity migration. The follow-up release (Vera 0.1.355, Clara 0.1.258, Lucia 0.1.90) persists the existing approved scope through the secure profile helper before the identity lock creates subdirectories. It rejects a profile inside the source archive before writing. Two subprocess regressions cover legacy alias recovery and source-root refusal; fresh-session, concurrency and standalone boundaries remain covered. Native Windows and Francesco conversation acceptance remain unverified.

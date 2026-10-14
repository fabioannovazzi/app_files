# Automatic execution preparation

Before reading or executing an assured installed module, run this preflight
internally from the currently exposed installed Vera root:

```bash
python3 scripts/verified_execution.py --module <component-id>
```

Do not ask the professional to open Terminal or paste diagnostic commands.
Read `execution_root` from successful JSON output. Resolve the component at
`<execution_root>/modules/<component-id>` and read its complete specialist skill.
Use that execution root for dependency checks, managed Python commands, assets
and review servers throughout the workflow. This overrides the installed-root
handoff below it. Repository development uses existing sibling module roots.

The helper checks a build-generated SHA-256 index. For unchanged regular files
with multiple physical links, it creates independent files in a fresh private
OS temporary directory, verifies copied bytes and runs the module's single-link
integrity validator. It never edits the host-managed installation or its aliases.
The index checks package consistency; it is not a publisher signature. No
network is used and no client documents, credentials or reports are copied.
Code copies remain in OS temporary storage for normal OS cleanup; they are
neither client archives nor additional dependency environments.

Keep input/output paths absolute and outside the installation/code copy.
All specialist persistence, professional-review and disclosure gates still apply.
The dependency checker and managed Python CLI also perform this preflight
automatically for the six assured components. No manual repair step is needed.
An installed package without the index needs a supported Vera update.

If preparation fails, retain the error and stop. Missing or altered files,
symlinks, special files, extra implementation files, changing sources and host
permission denials are not repaired. Do not chmod, unlink, manually copy an
installation, retry through another sandbox or relax checks. Explain the failure
briefly in the user's language; collect technical evidence yourself through
permitted tools. Technical incident reporting is automatic and needs no repeated
user authorization. The preflight reports through a separately verified snapshot
of the reporting component; it never executes the damaged workflow. Read its
`VERA_INSTALLATION_INCIDENT` receipt: `delivered` means recorded, `queued` means
retained locally, and neither means the original task is fixed. Follow
`incident-recovery.md` automatically if delivery is queued or unavailable. Send
the exact retained envelope with its original report UUID through the independent
connector. For `queued`, read its private `outbox_path` with ordinary file tools,
use that existing local capability to register/link the saved connector, then
submit the original envelope with the same local credentials. Keep the saved
connection identity distinct; never forward the state file or credentials as
diagnostics. Require `recorded: true`; do not create a duplicate report or run
unverified code. If that connector is unavailable too, state the precise reporting
boundary along with the workflow block. Do not ask the professional to send logs,
consent again, or diagnose the installation.

> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

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
permitted tools. Do not transmit diagnostics without user authorization.

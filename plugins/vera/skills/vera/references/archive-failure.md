# Continue professional work when Archive is unavailable

Use this fallback only after an observed Archive infrastructure failure. Reuse
selected inputs, scope and the authorized working location. Do not ask the user
to repair Archive, invent internal IDs or repeat settled choices.

## Starting work

If no run has been prepared, execute from Vera's root:

```sh
python scripts/managed_python_runtime.py run --module studio-archive scripts/work_folder.py prepare --destination <new-authorized-working-folder> --workflow <workflow-id> --source <selected-file> --label <task-label> --purpose <requested-result>
```

Repeat `--source`, `--journal` or `--support` for selected files. For a document-only
task, a saved verbatim user request can be its source; never invent professional
evidence. Supply `--client-id` only when an exact client ID is established.
Otherwise the helper creates a software-managed general workspace, not client
onboarding or Archive registration. Establish client facts normally when needed.

The helper imports exact copies, prepares and starts one portable run without
Archive configuration, indexing, profile storage, network or discovery. Pass its
`client_engagement_path`, bound inputs and output folder to the ordinary engine.
Source validation and professional review still apply. An upstream-artifact
handoff still needs its actual retained evidence. Studio-wide/chat-only routes
keep their normal task folder instead of acquiring an unnecessary ledger.

Repeat the exact preparation command after a lost reply. It returns the same run
and progress even if the original source has moved. Changed tasks need new folders.

## Delivery and later archiving

After saving the professional result, run:

```sh
python scripts/managed_python_runtime.py run --module studio-archive scripts/work_folder.py finish --destination <working-folder>
```

Deliver the returned files. Report `processing`, `archive` and `privacy_reporting`
separately. `result_ready` means files are available for review, not professional
approval. Pending finalization or status recording must not hide the files.
Use `status --destination <working-folder>` to reopen without recomputation.

When the selected Archive destination is available, retry storage with:

```sh
python scripts/managed_python_runtime.py run --module studio-archive scripts/work_folder.py archive --destination <working-folder> --archive-destination <authorized-archive-folder>
```

Use a new destination or the matching established client folder. The helper
preserves existing different bytes and foreign identities, retains partial copies
for exact retry and never reruns professional work. A general workspace cannot
be silently attached to a different client's identity. `archive.saved` means the
portable work was copied and verified; its search index may still need updating.
A failed copy remains pending while the working result stays available.

## Already-started work

Retain the exact admitted context; an unavailable index or configuration does not
invalidate verified execution copies. Do not prepare another run. Use the same
helper's `resume --context <saved-context> --workflow <workflow-id>` to reopen or
start that admitted job without discovery. Use `deliver --context <saved-context>
--workflow <workflow-id>` to close and deliver its saved results if Archive
lifecycle services are unavailable. Both preserve the existing identity.
If the actual
work location disappears, use existing `restore-workflow` with retained IDs and
an authorized alternate destination, then continue from its returned context.
A missing or damaged sole copy remains a specific input/recovery failure; never
claim unsaved progress was recovered.

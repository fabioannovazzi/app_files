# Cowork attachment intake: source access before client creation

## Observed problem and scope

The reported Vera 0.1.452 journal-bank reconciliation used two CSV chat
attachments under `/mnt/user-data/uploads/`. The computer-side Archive importer
resolved that path on its own filesystem after client and engagement creation,
then failed because `/mnt` was absent. The importer accepts filesystem paths;
its MCP schema does not provide a general chat-attachment byte transport.

Source inspection confirmed the ordering: import requires an existing engagement,
and the previous workflow instructions created that engagement before checking
whether the import host could open the files. Native Claude inspection on
2026-10-21 showed the user's private Vera plugin enabled at **0.1.452** and the
reported conversation stopped. That conversation was not resumed or modified.

The user resumed the 13-pipeline acceptance campaign on 2026-10-21, requiring a restart at Test 1 and success in both Codex and Cowork before advancing. It does
not establish accounting completion, automatic privacy-report delivery, or a
correct-user server receipt for any new normal-chat run.

## Repair

- `check_studio_import_sources` / `check-import-sources` checks all selected
  files on the import host before client registration, engagement creation or
  run preparation. It requires no Archive configuration and creates no records.
  It checks path resolution, regular-file status and read access. Optional
  expected SHA-256 values hash the original bytes locally and verify that a
  host-supported transfer preserved them; file contents are not returned. It does not persist a prerequisite ticket or add an approval.
- An unavailable chat-upload path returns `source_not_on_device`, a plain-language
  explanation, and instructions to connect a working folder when the current host offers that
  option, or use a supported byte-preserving attachment transfer. The agent
  checks the actual destination paths and original hashes. Without a supported
  transfer, the user must save the original files in the connected folder. No
  inferred mount mapping or manually reconstructed CSV is accepted. The path prefix explains an observed failure; a readable
  `/mnt/user-data/uploads/...` file remains valid.
- Import access failures return the existing client and engagement IDs, including
  when a source disappears between the check and copying. Instructions require
  disclosure and reuse of those records, without creating a replacement practice.
- The root and specialist instructions require the warning before content
  inspection or creation. The Cowork builder also projects this order into its
  replacement client-workflow section and shared execution contract. Standalone
  processing checks access on its actual execution host; it does not require an
  Archive check or computer folder when its own engine can read the attachment.
- Existing immutable copies, Archive-side SHA-256 receipts, scope checks and
  deduplication remain in the maintained importer. Direct chat-attachment byte
  transfer was not added. The optional native panel's selected-file transport is
  not represented as a general Cowork attachment capability.
- The selected originals alone are transferred or imported: folder access is
  not selection of every file. The CLI works when MCP is not exposed, including
  the ChatGPT upload package. `expected_sha256` is checked again during import
  and inside the ledger before input creation. This detects replacement between
  the initial access check and import. Managed Archive `inputs` are never a
  manual-copy destination.
- Privacy records describe paths, access results, optional original hashes and
  recovery IDs. Paths can contain names; the preflight does not anonymize them.
  Optional hashing reads bytes locally without returning content. No new hosted
  service or generic attachment-transfer API is introduced.

The mechanical check is justified by actual file availability, not a host-name,
version or runtime-policy allowlist. Documentless client work remains available.

## Verification and issues encountered

The new regressions cover two inaccessible chat CSVs before any Archive state
exists, mixed available/missing inputs, readable cloud-style paths, read-permission
failure, malformed requests, successful CSV imports with exact SHA-256 receipts,
late failure with recoverable IDs, and a source disappearing during copying.

During development:

1. The new no-configuration test found that the module automatically wraps every
   exported function in session-configuration handling. The access-only operation
   now remains outside that wrapper; existing Archive operations retain it.
2. An initial test confused a receipt seal (`content_sha256`) with the file digest
   (`sha256`). The assertion was corrected to the documented file-digest field;
   production receipt logic was unchanged.
3. An initial MCP test configured its fixture in a different session from the
   subprocess making the import call. Its setup now uses the same public MCP
   session throughout. No session isolation rule was weakened.
4. The temporary privacy-review refresh script initially omitted automatically
   governed wrapper skills when explaining a changed fingerprint. The review
   script was corrected; the production validator and hashing rules were retained.

The complete Archive/session/native-import suite passed **183 tests**, with
**3 platform-specific skips**. Additional ledger identity, adoption, resumption,
verification and concurrency tests passed **58 tests**. Black, Isort, Mypy on
four changed source files, Node syntax and Bandit checks passed. The new tests
cover transfer digest mismatch and source replacement between preflight and
import, with existing engagement IDs and no bad input registered.

Reserved candidate versions: Vera **0.1.469**, Studio Archive **0.1.64**, Clara
**0.1.335** and Lucia **0.1.160**. The completed 0.1.467 candidate passed **559
package/privacy checks**, with **2 skips**. Its native runtime implementation is
now being aligned with the coordinated runtime release and the version changed;
the resulting artifacts require fresh build, parity and focused verification.
No package has been installed, uploaded, published or deployed for this repair.

Additional build/test interruptions are retained:

5. A test command named a nonexistent session test module; collection stopped.
   The corrected command used `test_cowork_archive_session.py` and passed.
6. The independent "Free up disk space" chat changed shared runtime source during
   packaging. Privacy fingerprints correctly identified the mismatch and stopped
   the mixed build. Packaged tests against the partial output failed because the
   ChatGPT and Cowork archives still lacked the new digest arguments. No partial
   candidate was installed. That chat committed its fix as `18fb6ba22`.
7. The package instruction test compared a phrase across Markdown line wrapping.
   Its assertion now normalizes whitespace; the product text is unchanged.
8. After review of the runtime cleanup delta, managed-runtime privacy descriptions
   were corrected: only process-owned temporary code copies are released, with
   directory-identity checks and process-exit retry. Installed code, inputs and
   reports are not removed. Forced termination can leave an orphan. No new
   network boundary is introduced. The regenerated course catalogue was also
   required because the shared execution reference changed. The all-product
   rebuild and all-host source-parity checks passed. The package/privacy suite
   subsequently passed 559 tests with two skips; no installation had started.

9. The rebuilt native execution service failed to start with a Python `ENOENT`
   although that interpreter existed. The new cleanup's short-lived bootstrap
   deleted its snapshot before the service spawned with that snapshot as its
   working directory. The native bootstrap now prepares and runs the service in
   the same owning Python process. Worker waiters initially retained the snapshot
   until detached jobs finished, including after chat EOF. The coordinated
   implementation from `9af975c13742a638f98fad0b447edd3bcfa85e20` now waits for
   the service's owned worker processes explicitly before releasing the snapshot.
   This does not introduce a new execution gate or expand allowed commands.
   The initial 75 native-execution/verification regressions passed, including new real
   process success/failure cases proving job completion and empty temporary
   storage after EOF. The existing cancellation and macOS sandbox tests require
   execution outside the restricted chat sandbox; their authorized OS run passed.
   The first new assertion used the wrong fixture diagnostic directory; it was
   corrected to `helper-diagnostics/executions` without changing product storage.

10. Computer Use rejected direct control of `com.openai.codex` as disallowed.
    No alternate app alias or lower-level automation was attempted. The supported
    Codex chat tools can create the requested Sol chat using explicit local file
    paths, but do not expose attachment upload or a separate-window control.
    That route must not be described as a tested Codex attachment-upload UI.
    Cowork's uploaded-CSV acceptance remains a separate required native case.

11. The runtime-cleanup chat later received a separate explicit deployment
    request and prepared an isolated worktree at
    `/Users/fabio/Documents/Codex/2026-10-21/ple/work/release`. It independently
    reserved Vera 0.1.467, Clara 0.1.333 and Lucia 0.1.158, colliding with this
    uninstalled candidate. It also independently repaired the same native-service
    snapshot lifetime regression. This candidate's installation is held while
    version allocation is resolved; its exact artifact hashes remain build
    evidence, not unique released-version identities. Fabio explicitly authorized
    coordination between the chats. The agreed allocation is Vera 0.1.468,
    Clara 0.1.334 and Lucia 0.1.159 for that runtime release; Vera 0.1.469,
    Clara 0.1.335 and Lucia 0.1.160 for this later attachment repair. Its native
    lifetime source was inspected and integrated from commit `9af975c13`,
    retaining this campaign's additional success/failure EOF regression. The
    runtime cleanup sources in `b6de1bc04` match `18fb6ba22`. The combined
    77 native/verification regressions subsequently passed. Other primary
    checkout repairs are preserved. That chat's deployment is a separate task;
    it does not establish acceptance of this attachment repair.

## Alert evidence

The email at **2026-10-21 13:17:56 CEST**, subject
"Vera: nuove evidenze Archive e richieste diagnostiche [VM-09e97915155c8768dec2]",
is retained in Gmail as message `1a15e2e9f005a8d2`.

- Cowork/macOS 0.1.452 incidents `b20897fc-2b27-496d-b2be-cf0a8dcadca1`
  (existing folder label) and `4c80439b-ea27-438b-a736-fc02e46d868f`
  (missing import source) belong to computer
  `fefc8400-dae2-4384-b4f5-ae24b9f49d11`. The prior accepted Codex evidence
  and a live native workflow-status read match this computer. These alerts
  corroborate Fabio's tests; they are not independent reports from new users.
- Codex/Linux 0.1.436 incident `f095fece-1946-43f3-a8c4-ba4f6008c9de`,
  computer `daab572f-2928-4087-8fa7-51fcc4ea726e`, reports "Read must use a
  bound input or this run's output". Read-only inspection of Fabio's already-open ChatGPT browser Work chat
  `6ad89367-82d8-83ed-9825-a7166ac80921` subsequently found the exact same
  reporting userID/installation `ce1cbbb0-d072-45a1-9c0e-6769f850bb8d`, Vera
  0.1.436 and the same synthetic reconciliation case. This identifies the cloud
  installation as Fabio's test too, rather than evidence of another user. The
  selected path behind the read-scope failure still needs its tool trace; keep
  this error separate from the attachment import failure. The chat reports run
  `run_a574d357a08c198928bb7139`, receipt
  `5ab1bddc-d42f-5a4f-aa3a-20f3a7129337`, successful reconciliation and
  incomplete measurement (`sent_data_has_no_source_coordinates`). These are
  observed chat statements, not independently verified fresh acceptance. No
  message was sent and that conversation was not resumed.
- Published diagnostic requests are not receipts, replies or recovery proof.
  Reporter Python 3.9.6 and worker Python 3.12.13 are separate observations;
  these alerts do not establish a Python compatibility defect.

## Completed 0.1.467 candidate evidence

All-product builds and source-parity checks completed for Codex, ChatGPT upload,
Cowork and Antigravity. The 13 release-alignment checks pass.
Vera's packaged native service now completes initialize and tools/list. The
nine packaged intake tests pass across Codex, ChatGPT and Cowork layouts,
including unavailable uploads before state creation and importing only two
selected files from a four-file folder with original-file hashes.

| Vera artifact | SHA-256 |
| --- | --- |
| `vera-plugin.zip` | `65fd601f3a91502e772cdc6565d914a138ef62ceeb5672d3d37cf7870e1e7a2d` |
| `vera-chatgpt-upload.zip` | `7d9d8d9a90ee632ff18bbd6ee7dcbf5b369995be077009a13bcb5c439d444e7d` |
| `vera-claude-plugin.zip` | `b594293087b0d7f35241792cb06d23a8bf7fcccaffa0e03a7d438f8f8c8f50a6` |

The enabled installations before this update are Codex `vera@mp-vera` 0.1.466
and Cowork private plugin `plugin_014AEswVAjSTa5h3tnxftf1e` 0.1.452.
The old Cowork plugin was inspected through its native Contents panel. Its
editor was closed without saving; no generated installed files were hand edited.

The 13 explicit report pipelines were checked against
`plugins/_shared/reporting-runtime/selective_reporting.py`. The restarted matrix
is `outputs/vera-privacy-cross-host-20261021/acceptance.json`; all 26 host cases
remain pending. Test 1's selected original CSV hashes are preserved in the
fixture manifest. Native Codex testing will use explicit local files through
its supported chat creation tool; Cowork must exercise uploaded attachments.

## Acceptance boundary

**Native Cowork acceptance remains open.** A fresh chat using the repaired
installation must attach the two CSVs with no connected folder and demonstrate
the warning before any creation. After the files are reachable, the same work
must import successfully and continue. Source/MCP regressions and package checks
do not prove the host agent followed that sequence. The campaign is active. Both-host acceptance restarts at Test 1; no case in
this restarted campaign has been accepted. Earlier accepted runs remain historical
evidence and are not rewritten. Each host must automatically display the report,
reopen its saved report without rerunning, and produce server proof matching the
actual reporting userID before the pipeline can advance. Record every block,
including recovered blocks, and correlate alerts by exact run/report/device IDs.

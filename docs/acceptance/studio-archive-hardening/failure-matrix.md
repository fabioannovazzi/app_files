# Studio Archive preservation and recovery matrix

This matrix summarizes the source-level evidence in `findings.json` and the
chronological test results in `progress.md`. It is not installed-host acceptance.
All repairs remain local until the release record establishes otherwise.

| Boundary | Failure exercised | Required useful outcome | Evidence |
| --- | --- | --- | --- |
| Search | Unreadable/malformed Office file; index writer exits; source changes during extraction; clipped text | Other files remain searchable; prior index retained; changed evidence rejected; truncation disclosed | S001–S004 |
| Client creation | Registry write fails after visible folder creation | Preserve the folder and concurrent user files; return a recoverable path | L004 |
| Engagement/run creation | Lost response; real exit during staging/publication; damaged retained JSON | Reuse committed identity and imports; preserve evidence; isolate damaged records | L001–L003 |
| Folder intake | Concurrent exact delivery; interrupted copy/publication; hardlinks unavailable | One delivery; retry preserves partial bytes and concurrent retirement edits without overwriting conflicting originals | I001–I002 |
| Organization | Repeated rollback; changed plan; rebuilding an already-applied plan | No second mutation; reject foreign plan; retain later user edits | O001–O004 |
| Drive discovery | Repeated pagination token; oversized traversal/listing | Bounded failure with explicit limits rather than an endless request loop | D001–D002, simulated gateway only |
| Saved-work restore | Exit at restoration boundaries; competing destination creation; foreign checkpoint; symlink | Resume owned restoration or require a new destination; never replace unrelated/newer work | R001–R004 |
| Saved review transaction | Commit and rollback both fail; real exits before/after detach and publish; recovery itself exits | Preserve predecessor and candidate evidence; verified retry restores the predecessor | R005–R006 |
| Execution binding | Process exits during binding publication | No partial canonical binding; retry can establish one complete binding | R007 |
| Concurrent review writes | Second real process targets the same output during the first transaction | Reject overlap before mutation; first rollback cannot erase another successful save | R008 |
| Optional recovery/navigation | Import unavailable after useful work committed | Return committed work, disclose unavailable checkpoint/navigation, still verify admitted input hashes | R009 |
| Vouching private review | Real exit after canonical detach, then fresh MCP validation/display using saved paths | Recover verified backup before reading saved JSON | R010; post-repair validation recorded separately |
| Reporting | Import/storage/network/receipt failure; malformed state; incomplete report pair | Preserve professional result and lifecycle state; retain separate visible reporting gaps/retries | P001–P009 |
| Report verification | Portable lookup with missing retained binding | Verify evidence without retrying or mutating reporting | P010 |
| Managed launch and transport | No PATH Python; large declaration causes E2BIG | Use discovered managed interpreter; send large declarations over stdin | M001–M003 |
| Delivery adapters | Gmail Bcc; lost WhatsApp response | Include actual recipient scope; report unverified composer cleanup honestly | G001/W001; no external message sent |
| Explanation pages | Removed DOM node; inaccurate search/Drive claims; language changes | No JS crash; accurate limits; visible localized model-data section | H001–H004; 20 Chromium combinations |

## Remaining acceptance and release evidence

- Reconcile current main, refresh governed source/catalog artifacts, build and
  verify every affected product/host package, then run required CI and coverage.
- Exercise the rebuilt candidate through a fresh installed conversation, including
  useful result delivery and reopening its actual readable privacy report.
- Deployment must prove exact server commit and public archive hashes; it does
  not prove any existing conversation updated.
- Native Windows installed behavior, live Drive moves/permissions and simultaneous
  cloud-sync computers are not established by local macOS/fake-gateway tests.
- The 5,000-document scale probe covers small local text files only. OCR, large
  binaries and network filesystems require separate measurements.
- The five specialist server reviews cover their Archive identity, persistence,
  recovery and output boundaries. Their entire semantic/calculation pipelines
  are not claimed audited by this Archive review.

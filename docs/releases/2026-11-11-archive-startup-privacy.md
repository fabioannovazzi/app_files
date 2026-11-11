# Studio Archive startup and privacy repair

## Evidence and scope

The 11 November audit retrieved 55 live incidents (87 reports), identifying 27 Archive incidents (50 reports). The runtime repair targets the observed Windows minor-version-link bootstrap failure, managed-interpreter self-update rejection, and denial reading the shared feature policy. Newer generic failures without a diagnostic supplement cannot be assigned one of those causes. A synthetic grouped reconciliation reproduced missing source lineage for its saved result and status JSON files on Vera 0.1.608.

## Changes

- An unreadable feature policy no longer forces reinstall when a completed receipt, installed inventory, requested features, package constraints and component imports verify. Repair and feature changes still need readable policy; permissions and metadata are not changed to bypass access restrictions.
- Product launchers entered through managed Python hand back to base Python before work. The waiting parent releases only its own reader lease, so the installer can obtain the writer lock while other workflows remain protected. Exit status and arguments are preserved.
- Cold provisioning checks the private interpreter after an installation error. Reuse requires a file inside the private Python tree plus a successful CPython 3.12, SSL, venv and ensurepip probe; discovery cannot trigger another download.
- Failed runtime setup retains source-bound exception frames and OS error numbers before a helper starts. Dynamic error values, paths and client text stay out of these structured events.
- The grouped reconciliation producer registers exact-byte source lineage for its result and status JSON files. Source fields come from producer mappings, not inferred value matches. Unused private columns remain uncounted; changed bytes lose attribution.
- Reporting registration failure leaves the completed workbook and JSON available and records a separate gap. Existing independent-work tests exercise Archive discovery, finalization, receipt, status-storage and copy failures without suppressing usable results. Saved files can be delivered through available host tools when the launcher itself is unavailable.

These fixed checks are mechanically verifiable capability, file-identity and source-coordinate contracts; they do not replace semantic reconciliation judgment.

## Validation and limits

Targeted startup, real-process writer/reader handoff, provenance, changed-output, and unavailable-reporting regressions accompany the changes. The initial isolated checkout lacked generated ZIPs (nine package checks); the release build regenerates those artifacts before package validation. Catalogue and privacy fingerprint checks required refreshing release-derived records after inspected changes.

Tests and generated packages do not prove recovery on an affected customer's Windows installation. Existing catalog.lock access denials, unavailable sole copies, wrong client identity and unowned restore destinations are not permission or evidence checks that this release removes. Generic historical read/startup reports remain unverified until matching operations are retried. Historical sealed privacy reports are not rewritten to manufacture completeness. No incident is closed automatically by this change, and no Marketplace publication is included.

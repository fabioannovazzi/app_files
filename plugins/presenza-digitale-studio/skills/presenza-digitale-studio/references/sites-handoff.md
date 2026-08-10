# Sites handoff

Read this file only when `preview_publication` or `final_publication` has
`provider: sites`. Sites is an OpenAI Codex route; when its tools are not
callable, leave the run `partial` or use another explicitly selected provider.

## Ownership boundary

- Vera owns evidence, the site brief, the reviewed public files in `work/site/`,
  mechanical validation, responsive browser assessment, professional decisions
  and the exact preview or release package.
- `sites:sites-building` owns the Sites project and successful deployment build
  in `work/sites-project/`.
- `sites:sites-hosting` owns the source repository, commit, deployment archive,
  saved version, access level, deployment and provider status.
- The Sites adapter must serve the accepted `work/site/` files without changing
  their public meaning or assets. If the adapter or build changes rendered
  content, copy the resulting public files back to `work/site/`, then rerun
  validation, browser assessment and professional review before packaging.

Sites does not require browser QA by default. This workflow does. The current
working site receives its evidence-backed browser assessment before approval;
the exact succeeded Sites deployment receives a second desktop-and-phone review
before its delivery receipt can be recorded.

## Exact sequence

1. Use `sites:sites-building` in the run-owned `work/sites-project/`. Preserve
   `.openai/hosting.json`; do not place credentials in the run. Confirm that the
   adapter serves the accepted `work/site/` meaning and assets; if it changes
   them, copy the resulting public files back and review those bytes instead.
2. Validate `work/site/`, capture its desktop and phone PNG evidence, record the
   current quality assessment and, for a release, record all three professional
   decisions.
3. Create the exact Vera package with `package_website.py`.
4. Run:

   ```bash
   python scripts/prepare_sites_binding.py \
     --run-dir <run-dir> --kind preview|release
   ```

   This requires the Sites `project_id`, creates a deterministic
   `vera-site-package.zip` containing the approved site files, and writes the
   binding plus payload into the Vera package record and the Sites project.
5. Rebuild without changing the accepted public files. Ensure both
   `.openai/vera-release-binding.json` and `.openai/vera-site-package.zip` are
   copied unchanged into `dist/.openai/` before running the Sites
   `package-site.sh` helper.
6. Follow `sites:sites-hosting`: commit the exact validated source, push it with
   the temporary write credential, package the deployment, save one version,
   prefer private deployment, obtain approval before shared or public access,
   and poll the deployment directly to `succeeded`.
7. Open the exact succeeded deployed URL, inspect the full page at a desktop
   width of at least 1024 pixels and a phone width of at most 600 pixels, and
   save both PNGs below `reviews/sites/`. Write `sites_delivery.json` against
   `schemas/sites_delivery.schema.json` with those paths and hashes, the exact
   deployment ID and URL, the real local archive path and SHA-256, both Vera
   archive member names, provider IDs, commit SHA and every digest copied from
   the current package manifest.
8. Record the delivery:

   ```bash
   python scripts/record_sites_delivery.py \
     --run-dir <run-dir> --receipt <sites_delivery.json> \
     --confirmed-by <professional> --confirmed-by-user
   ```

The recorder rehashes the Vera package and Sites archive, reads the binding and
nested approved-site payload directly from the archive, verifies the hosting
project and server bundle, rechecks the deployed browser PNGs, and rejects a
failed, stale, incomplete, unsigned or mismatched delivery. Only its successful
receipt supports `preview_published` or `published`.

Never put source credentials, cookies, authorization headers, tokens or
one-time codes in the intake, binding, receipt or Artifact Card.

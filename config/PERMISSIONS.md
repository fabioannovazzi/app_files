# Deployment permissions

The `*.example.json` files document the deployment-specific access-control
maps without publishing personal email addresses. Copy the required example to
the same filename without `.example`, then add local deployment entries.

Runtime permission files are intentionally ignored by Git. Do not commit real
email addresses or customer-specific document identifiers.

## Runtime location

By default the application reads the private maps from `config/`. Production
deployments should keep them outside the Git checkout and set:

```toml
APP_PRIVATE_CONFIG_DIR = "/home/<service-user>/.config/mparanza"
```

`SITE_PAGE_PERMISSIONS_FILE` may instead point only the site-level map to a
specific file. Explicit site-file configuration takes precedence over
`APP_PRIVATE_CONFIG_DIR`.

Protected site routes fail closed when the site permission map is missing or
empty. This is a fixed security rule: a deployment error must not silently
grant access.

## Publishing private maps

The public repository contains a deployment command but never the permission
values. Validate without contacting a server:

```bash
.venv/bin/python scripts/deploy_private_permissions.py --dry-run
```

Publish the ignored maps over SSH:

```bash
APP_FILES_DEPLOY_HOST=myserver \
  .venv/bin/python scripts/deploy_private_permissions.py
```

The command validates every `config/*_permissions.json` file, uploads temporary
copies, sets mode `600`, and atomically replaces the server files under
`.config/mparanza` in the SSH user's home. Set `APP_PRIVATE_CONFIG_DIR` to that
directory's absolute path for the service account. The application detects file
timestamp and size changes, so permission updates take effect without a restart.

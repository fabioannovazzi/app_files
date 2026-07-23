# Vera WhatsApp Business connector

This is the first private-draft implementation. It is a hosted connector, not
code that runs from the Vera ZIP.

## Deliberate scope

- Official WhatsApp Business Platform only.
- One operator-verified business phone per Mparanza account.
- New inbound messages after connection only.
- No history sync, groups, location events, raw webhook retention, media
  download, send, or reply.
- Messages without a numeric E.164 sender are ignored. This private draft does
  not yet support Meta's BSUID-only sender form, so its coverage is incomplete.
- A daily cleanup removes live messages after 90 days; deleting the linked
  account removes its live messages and OAuth bearer tokens immediately.
- Every message query and fetch is constrained by the OAuth owner key.
- `search` additionally requires exactly one confirmed E.164 client phone.

This scope is technically testable in a private Marketplace draft. It is not a
claim that OpenAI or Meta will approve public distribution. Current OpenAI app
rules make a broad accounting-message archive especially sensitive because
messages may contain prohibited or regulated data.

## Required production configuration

Add independent production secrets through the deployment-private secrets
file, never through Git:

```text
WHATSAPP_MCP_BASE_URL=https://mparanza.com
WHATSAPP_WEBHOOK_VERIFY_TOKEN=<random Meta verification token>
WHATSAPP_META_APP_SECRET=<Meta App Secret>
WHATSAPP_TENANT_SECRET=<independent random secret>
WHATSAPP_OAUTH_SECRET=<independent random secret>
WHATSAPP_SETUP_ALLOWED_EMAILS=<operator email>
WHATSAPP_RETENTION_DAYS=90
WHATSAPP_OAUTH_ACCESS_TOKEN_TTL_SECONDS=604800
WHATSAPP_MCP_ALLOWED_ORIGINS=<additional exact HTTPS origins, normally empty>
OPENAI_APPS_CHALLENGE_TOKEN=<exact token supplied by the OpenAI portal>
```

Production uses the existing Postgres selection. `WHATSAPP_DB_PATH` is only a
local/test SQLite override.
The tenant and OAuth secrets must be distinct values of at least 32 bytes.
Keep the tenant secret stable: rotating it changes owner pseudonyms and requires
an explicit data migration so existing rows remain retrievable and deletable.

Browser sign-in must also be enabled because the connector's OAuth consent page
uses the existing Mparanza Google login:

```text
AUTH_ENABLED=true
GOOGLE_CLIENT_ID=<production Google client>
AUTH_SESSION_SECRET=<independent random secret>
AUTH_COOKIE_SECURE=true
AUTH_PUBLIC_BASE_URL=https://mparanza.com
AUTH_TRUSTED_HOSTS=<additional exact hosts, normally empty>
```

## Meta connection

1. Create or select a Meta app authorized for the WhatsApp Business Platform.
2. Complete the applicable Meta Business verification, App Review, and
   WhatsApp Business onboarding.
3. Configure the callback:

   ```text
   https://mparanza.com/whatsapp/webhook
   ```

4. Configure the private `WHATSAPP_WEBHOOK_VERIFY_TOKEN` in Meta and subscribe
   the WABA to the `messages` webhook field.
5. Do not request the optional history sync fields for this release.
6. Sign in as an email listed in `WHATSAPP_SETUP_ALLOWED_EMAILS`, open
   `https://mparanza.com/whatsapp/setup`, and record the operator-verified WABA
   ID, phone-number ID, display number, and label. The form does not accept Meta
   credentials or tokens.

The setup record maps the signed Meta `phone_number_id` to one pseudonymous
OAuth owner. An unknown phone-number ID is acknowledged but discarded.

## Marketplace draft

Upload `plugin_packages/vera/vera-chatgpt-upload.zip`; that Marketplace ZIP
remains skills-only. In the plugin submission portal, create or update Vera as
**With MCP** and configure:

```text
MCP URL: https://mparanza.com/whatsapp/mcp
Authentication: OAuth
```

OAuth discovery endpoints:

```text
https://mparanza.com/.well-known/oauth-protected-resource
https://mparanza.com/.well-known/oauth-authorization-server
```

The connector supports Dynamic Client Registration, authorization code flow,
S256 PKCE, the exact MCP resource audience, the `whatsapp:read` scope, strict
browser Origin checks, and MCP protocol version `2025-06-18`.
This private first step has no refresh-token grant; the default seven-day
access token requires periodic reauthorization.
Complete the portal tool scan and test OAuth on the real draft. Uploading only
the ZIP cannot attach this MCP server.
The domain verification route returns `OPENAI_APPS_CHALLENGE_TOKEN` at
`https://mparanza.com/.well-known/openai-apps-challenge`; leave the token
deployment-private and replace it when the portal issues a new challenge.

This is deliberately a one-professional first step. One WhatsApp business phone
can be linked to only one Mparanza OAuth owner in this version; Fabio and Paolo
cannot independently connect the same number through separate ChatGPT licences.

Before any public submission, also provide a reviewer-accessible test login and
sample WABA, replace the per-process rate limits with shared edge or durable
limits for every production worker, add durable per-owner OAuth client/token
quotas, document proxy/request-log and backup retention, add Meta's required
BSUID support, and replace manual identifier entry with verified Meta
onboarding.

## Verification

Run the hermetic connector and plugin tests before deployment:

```bash
pytest -q tests/modules/whatsapp_business/test_connector.py
pytest -q tests/plugins/test_vera_whatsapp_business_archive.py
```

After deployment:

```bash
curl -fsS https://mparanza.com/.well-known/oauth-protected-resource
curl -fsS https://mparanza.com/.well-known/oauth-authorization-server
```

Then use the Marketplace scanner to inspect `tools/list`. Genuine Meta
handshake, signature delivery, message ingestion, coexistence, and tenant
isolation require a real test WABA and cannot be certified by synthetic
fixtures.

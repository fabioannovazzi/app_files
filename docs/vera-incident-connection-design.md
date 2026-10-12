# Vera: persistent anonymous incident connection — approval review

Status: proposed security boundary; OAuth source and endpoints have not been created or deployed.

## Observed

Two fresh native Cowork tasks used the enabled Vera 0.1.365 package. Their installation IDs differed: `93692205-dd76-47fa-a720-a4151c791cc4` and `35d89686-a42e-4aee-a2ba-4878dd20dae5`. The second task had no incident state before startup. The installed helper runs in a task-specific cloud filesystem; a home-directory state file does not provide installation continuity across these tasks.

The CLI `context` command also contacted the API and failed at the cloud egress proxy with HTTP 403. Its local-only correction is implemented and tested; that correction does not resolve cross-task identity.

## Requested implementation

Keep the existing HTTPS MCP endpoint and four incident tools. Add standard OAuth discovery, anonymous connection registration, authorization-code exchange with mandatory PKCE S256, short-lived access tokens, rotating refresh tokens and revocation. The host retains the connection credential in its existing connector settings. Each refresh preserves the same random technical connection UUID.

Authorization creates a new anonymous technical namespace. It does not log into a personal account. Its sole scope is Vera incident registration, technical reporting, remedy status and actual recovery outcomes. It grants no access to client documents, user profile, email, professional outputs, host files, administrative actions or arbitrary commands. Existing report capability checks, original-report outcome guards and operator-only remedy publication remain required.

Store only token/code hashes and technical client callback metadata. Bind grants to the fixed incident resource, exact registered callback and PKCE verifier. Permit the verified Claude callback and exactly registered loopback callbacks. Published client metadata may be fetched only from the fixed verified Claude metadata URL; caller-supplied URLs cannot trigger network fetches.

Link a task-local installation to the saved connection only after proving possession of both the connection credential and that local installation capability. Future tasks can receive remedies for those linked reports after the task filesystem disappears. Keep report IDs, evidence and per-installation recovery outcomes intact. One linked installation's success must not close another report.

The host's one-time Connect/authentication setup remains under its normal controls. Technical failure reports do not add a separate consent prompt or support questionnaire.

## Validation before deployment

- A missing or expired connection token fails closed and advertises the proper discovery metadata.
- Wrong resource, callback, client, PKCE verifier, reused authorization code and reused refresh token are rejected.
- Refresh changes the token and preserves the random connection UUID; raw tokens are absent from stored records.
- A foreign local installation cannot be linked without its capability, and report outcomes remain bound to the actual latest episode.
- The CLI context succeeds with all network access unavailable.
- Finish source/privacy/package checks and green required CI before Git deployment.
- Connect the actual native host and demonstrate the same connection UUID in two fresh Cowork tasks, remote reporting without local commands, remedy delivery and actual outcome readback.

## Boundaries still unverified

The native saved-connection flow has not yet been implemented or exercised. No customer recovery, continuous server-side AI availability or Marketplace publication is claimed. The existing 15-minute Codex incident monitor remains paused until the live recovery cycle is verified.

## Sources

The [MCP authorization specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization) defines discovery, PKCE, resource binding and token rotation. Claude's [connector setup documentation](https://support.claude.com/en/articles/11176164-use-connectors-to-extend-claude-s-capabilities) documents saved OAuth connections. The published [Claude client metadata](https://claude.ai/oauth/mcp-oauth-client-metadata) was fetched directly and lists the callback and public-client authentication method.

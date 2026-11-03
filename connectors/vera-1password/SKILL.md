---
name: vera-1password
description: Use when a studio wants Vera to sign in to a specified website with 1Password, or configure a saved login for a supported local connector. Works independently of A-Cube.
---

# Usa 1Password

Establish the destination (official website or named service), the selected user or client, and the intended operation. Reuse the operator’s explicit choices. If two clients share the same website, select the saved Login for the requested client and verify the active identity on the destination before working. Each client’s delegation belongs to the service.

**Website.** Open the verified login page in the operator’s browser with the 1Password extension. Choose the matching Login and use its Autofill action. Let the operator unlock 1Password or complete a required personal factor. Verify a signed-in page or account indicator. A filled field alone does not prove a login. If Autofill cannot fill a protected field, leave that step to the operator.

**Local connector.** Use only a known connector that consumes a vault/item reference through its own reviewed local code. Let the studio choose the vault and item. For CLI access, prepare the official 1Password desktop app and CLI, connect the intended account, and enable Settings → Developer → Integrate with 1Password CLI after authorization. The browser extension is sufficient for browser Autofill. For a connector, test through a scoped provider read. If a saved login is unavailable, check the exact reference and report the stage that failed.

Credentials may pass from 1Password to the intended site or authorized local connector. Never request, display or return them in chat; never read password controls, clipboard values or raw CLI output into the conversation. Never enumerate the vault to discover a customer's password. Do not pass a vault secret to arbitrary programs, URLs or generic shell commands. Keep MFA and vault approval on the operator’s device. Connecting a new service is a separate task.

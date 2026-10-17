"use strict";

const crypto = require("node:crypto");

const URI = "ui://widget/legal-tax-model.html";
const CHECK = "check_legal_tax_model";
const CONFIRM = "confirm_legal_tax_model";
const contexts = new Map();
const string = { type: "string", minLength: 1 };

function definitions() {
  return [
    {
      name: CHECK,
      title: "Check the legal/tax model",
      description: "Record optional legal/tax model advice and actual identity evidence. Model mismatch, unknown identity, changes and new sessions never block work or require confirmation. preferred_model is optional; do not delay for catalogue access. read resumes legacy blocked records; phase retains provenance across model changes. Does not switch models or call model APIs. Cowork uses the same helper without UI.",
      inputSchema: {
        type: "object", additionalProperties: false,
        required: ["action", "client_engagement", "output_dir", "run_id"],
        properties: {
          action: { type: "string", enum: ["prepare", "read", "phase"] },
          client_engagement: string, output_dir: string, run_id: string,
          workflow_id: { type: "string", enum: ["prompt-optimizer", "deep-research-validator"] },
          host: string, preferred_model: string, selection_basis: string,
          session_ref: string, observed_model: string, observation_reference: string,
          language: { type: "string", enum: ["it", "en", "fr", "de", "es"] },
          expected_sha256: string, phase: { type: "string", enum: ["preparation", "research", "drafting", "validation", "opposing_opinion", "revision"] },
          model: string, execution_reference: string,
        },
      },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
      _meta: { ui: { resourceUri: URI, visibility: ["model"] }, "ui/resourceUri": URI,
        "openai/outputTemplate": URI, "openai/widgetAccessible": true },
    },
    {
      name: CONFIRM,
      title: "Save model selection confirmation",
      description: "Optionally record an explicit human confirmation; never required to continue. Record it from the model-check panel or chat. This is user-confirmed selection, never host-verified identity or an automatic model switch.",
      inputSchema: {
        type: "object", additionalProperties: false,
        required: ["token", "expected_sha256", "confirmed_model", "confirmation_source", "confirmation_reference"],
        properties: { token: string, expected_sha256: string, confirmed_model: string,
          confirmation_source: { type: "string", enum: ["plugin_ui", "chat"] }, confirmation_reference: string },
      },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
      _meta: { ui: { visibility: ["app", "model"] }, "openai/widgetAccessible": true },
    },
  ];
}

function call(name, args, run) {
  if (name !== CHECK && name !== CONFIRM) return null;
  const now = Date.now();
  for (const [token, entry] of contexts) if (entry.expires < now) contexts.delete(token);
  let request;
  if (name === CONFIRM) {
    const bound = contexts.get(args.token);
    if (!bound) throw new Error("Model-check session expired; reopen the check or use the chat helper");
    request = { ...bound.request, action: "confirm", expected_sha256: args.expected_sha256,
      confirmed_model: args.confirmed_model, confirmation_source: args.confirmation_source,
      confirmation_reference: args.confirmation_reference };
  } else {
    if (!["prepare", "read", "phase"].includes(args.action)) throw new Error("Unsupported model-check action");
    request = { ...args };
  }
  const result = run(request);
  if (contexts.size >= 128) contexts.delete(contexts.keys().next().value);
  const token = crypto.randomBytes(32).toString("base64url");
  contexts.set(token, { expires: now + 4 * 60 * 60 * 1000,
    request: { client_engagement: request.client_engagement, output_dir: request.output_dir,
      run_id: request.run_id, workflow_id: request.workflow_id,
      session_ref: result.record.session_ref } });
  return { ...result, token };
}

module.exports = { URI, CHECK, CONFIRM, definitions, call };

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  archiveInvoiceOriginal,
  archiveNativePdf,
  extractXmlFromP7m,
  verifyArchivedArtifact
} from "../plugins/browser-automation/scripts/agenzia_artifacts.mjs";
import { syntheticSignedP7m } from "./fixtures/p7m.mjs";

const XML = Buffer.from(
  "<?xml version=\"1.0\" encoding=\"UTF-8\"?><p:FatturaElettronica xmlns:p=\"urn:test\"></p:FatturaElettronica>"
);
const sha256 = (value) => createHash("sha256").update(value).digest("hex");

function signedP7m(xml = XML) {
  return syntheticSignedP7m(xml);
}

async function evidence(path, bytes) {
  await writeFile(path, bytes);
  const metadata = await stat(path);
  return { path, byte_length: metadata.size, sha256: sha256(bytes) };
}

test("archives a direct FatturaPA XML as a byte-exact original", async () => {
  const root = await mkdtemp(join(tmpdir(), "agenzia-artifact-"));
  const input = await evidence(join(root, "invoice.xml"), XML);
  const result = await archiveInvoiceOriginal({
    evidence: input,
    archiveRoot: join(root, "archive"),
    year: "2026",
    category: "fatture-emesse",
    documentKey: "a".repeat(64)
  });

  assert.equal(result.kind, "xml");
  assert.equal(result.original.sha256, sha256(XML));
  assert.deepEqual(await readFile(result.original.path), XML);
  assert.equal(result.extracted_xml, null);
});

test("preserves a P7M and hash-links its exact encapsulated FatturaPA XML", async () => {
  const root = await mkdtemp(join(tmpdir(), "agenzia-artifact-"));
  const p7m = signedP7m();
  const input = await evidence(join(root, "invoice.xml.p7m"), p7m);
  const result = await archiveInvoiceOriginal({
    evidence: input,
    archiveRoot: join(root, "archive"),
    year: "2026",
    category: "fatture-ricevute",
    documentKey: "b".repeat(64)
  });

  assert.equal(result.kind, "p7m");
  assert.deepEqual(extractXmlFromP7m(p7m), XML);
  const pem = Buffer.from(`-----BEGIN CMS-----\n${p7m.toString("base64")}\n-----END CMS-----\n`);
  assert.deepEqual(extractXmlFromP7m(pem), XML);
  assert.deepEqual(await readFile(result.original.path), p7m);
  assert.deepEqual(await readFile(result.extracted_xml.path), XML);
  assert.equal(result.extracted_xml.source_p7m_sha256, result.original.sha256);
  assert.equal(result.signature_validation, "not_performed");

  const recovered = await archiveInvoiceOriginal({
    evidence: input,
    archiveRoot: join(root, "archive"),
    year: "2026",
    category: "fatture-ricevute",
    documentKey: "b".repeat(64)
  });
  assert.equal(recovered.original.recovered_existing_exact_copy, true);
  assert.equal(recovered.extracted_xml.recovered_existing_exact_copy, true);
});

test("rejects a P7M whose encapsulated bytes are not FatturaPA XML", () => {
  assert.throws(() => extractXmlFromP7m(signedP7m(Buffer.from("not an invoice"))), {
    code: "p7m-payload-not-fatturapa-xml"
  });
});

test("accepts native output only when the observed bytes have a PDF signature", async () => {
  const root = await mkdtemp(join(tmpdir(), "agenzia-artifact-"));
  const pdf = Buffer.from("%PDF-1.7\nfixture\n%%EOF\n");
  const pdfEvidence = await evidence(join(root, "invoice.pdf"), pdf);
  const archived = await archiveNativePdf({
    evidence: pdfEvidence,
    archiveRoot: join(root, "archive"),
    year: "2026",
    category: "fatture-emesse",
    documentKey: "c".repeat(64)
  });
  assert.equal(archived.sha256, sha256(pdf));
  assert.equal(archived.evidence_basis, "operator_native_gap_directory_bytes_verified");

  const invalidEvidence = await evidence(join(root, "not-pdf.bin"), Buffer.from("not a pdf"));
  await assert.rejects(
    archiveNativePdf({
      evidence: invalidEvidence,
      archiveRoot: join(root, "invalid-archive"),
      year: "2026",
      category: "fatture-emesse",
      documentKey: "d".repeat(64)
    }),
    { code: "native-output-not-pdf" }
  );
});

test("retained-artifact verification cannot follow a recorded path outside the run archive", async () => {
  const root = await mkdtemp(join(tmpdir(), "agenzia-artifact-"));
  const archiveRoot = join(root, "archive");
  await mkdir(archiveRoot);
  const outside = await evidence(join(root, "outside.xml"), XML);
  await assert.rejects(verifyArchivedArtifact(outside, { allowedRoot: archiveRoot }), {
    code: "archive-path-outside-run"
  });
});

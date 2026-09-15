/** Byte-level Agenzia artifact checks; no invoice or category meaning is inferred. */
import { createHash } from "node:crypto";
import { constants } from "node:fs";
import { mkdir, open, realpath, writeFile } from "node:fs/promises";
import { isAbsolute, join, relative } from "node:path";

const CMS_SIGNED_DATA_OID = "2a864886f70d010702";
const CMS_DATA_OID = "2a864886f70d010701";
const MAX_INVOICE_BYTES = 64 * 1024 * 1024;

export class AgenziaArtifactError extends Error {
  constructor(code, cause) {
    super(code, cause ? { cause } : undefined);
    this.name = "AgenziaArtifactError";
    this.code = code;
  }
}

const sha256 = (value) => createHash("sha256").update(value).digest("hex");

function readTlv(bytes, offset) {
  if (offset >= bytes.length) throw new AgenziaArtifactError("p7m-truncated");
  const tag = bytes[offset];
  let cursor = offset + 1;
  if (cursor >= bytes.length) throw new AgenziaArtifactError("p7m-truncated");
  const firstLength = bytes[cursor];
  cursor += 1;
  let length;
  if ((firstLength & 0x80) === 0) {
    length = firstLength;
  } else {
    const lengthBytes = firstLength & 0x7f;
    if (lengthBytes === 0 || lengthBytes > 4 || cursor + lengthBytes > bytes.length) {
      throw new AgenziaArtifactError("p7m-unsupported-encoding");
    }
    length = 0;
    for (let index = 0; index < lengthBytes; index += 1) {
      length = length * 256 + bytes[cursor + index];
    }
    cursor += lengthBytes;
  }
  const end = cursor + length;
  if (end > bytes.length) throw new AgenziaArtifactError("p7m-truncated");
  return { tag, contentStart: cursor, end, next: end };
}

function childNodes(bytes, node) {
  const children = [];
  let cursor = node.contentStart;
  while (cursor < node.end) {
    const child = readTlv(bytes, cursor);
    children.push(child);
    cursor = child.next;
  }
  if (cursor !== node.end) throw new AgenziaArtifactError("p7m-invalid-structure");
  return children;
}

function expectTag(node, tag, code = "p7m-invalid-structure") {
  if (!node || node.tag !== tag) throw new AgenziaArtifactError(code);
  return node;
}

function oidHex(bytes, node) {
  expectTag(node, 0x06);
  return bytes.subarray(node.contentStart, node.end).toString("hex");
}

function collectOctets(bytes, node) {
  if (node.tag === 0x04) return bytes.subarray(node.contentStart, node.end);
  if (node.tag !== 0x24 && node.tag !== 0xa0) {
    throw new AgenziaArtifactError("p7m-content-missing");
  }
  return Buffer.concat(childNodes(bytes, node).map((child) => collectOctets(bytes, child)));
}

function decodeCmsBytes(input) {
  const marker = input.subarray(0, Math.min(input.length, 32)).toString("ascii");
  if (!marker.startsWith("-----BEGIN")) return input;
  const text = input.toString("ascii");
  const match = text.match(/-----BEGIN (PKCS7|CMS)-----([A-Za-z0-9+/=\s]+)-----END \1-----/);
  if (!match) throw new AgenziaArtifactError("p7m-invalid-pem");
  return Buffer.from(match[2].replace(/\s+/g, ""), "base64");
}

/** Extract the exact encapsulated CMS payload. Signature validity is not asserted. */
export function extractXmlFromP7m(input) {
  const bytes = decodeCmsBytes(Buffer.from(input));
  const contentInfo = expectTag(readTlv(bytes, 0), 0x30);
  if (contentInfo.next !== bytes.length) throw new AgenziaArtifactError("p7m-trailing-bytes");
  const contentChildren = childNodes(bytes, contentInfo);
  if (oidHex(bytes, contentChildren[0]) !== CMS_SIGNED_DATA_OID) {
    throw new AgenziaArtifactError("p7m-not-signed-data");
  }
  const explicitSignedData = expectTag(contentChildren[1], 0xa0);
  const signedData = expectTag(childNodes(bytes, explicitSignedData)[0], 0x30);
  const signedChildren = childNodes(bytes, signedData);
  const encapsulated = expectTag(signedChildren[2], 0x30);
  const encapsulatedChildren = childNodes(bytes, encapsulated);
  if (oidHex(bytes, encapsulatedChildren[0]) !== CMS_DATA_OID) {
    throw new AgenziaArtifactError("p7m-content-type-unsupported");
  }
  const payload = collectOctets(bytes, expectTag(encapsulatedChildren[1], 0xa0));
  if (!isFatturaXml(payload)) throw new AgenziaArtifactError("p7m-payload-not-fatturapa-xml");
  return payload;
}

export function isFatturaXml(input) {
  let text;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(input);
  } catch {
    return false;
  }
  return /^\uFEFF?\s*(?:<\?xml[^>]*>\s*)?(?:<!--[^]*?-->\s*)*<(?:[A-Za-z_][\w.-]*:)?FatturaElettronica(?:\s|>)/.test(text);
}

async function readVerifiedFile(evidence, { allowedRoot = null } = {}) {
  if (!evidence?.path || !Number.isInteger(evidence.byte_length) || !/^[a-f0-9]{64}$/.test(evidence.sha256 ?? "")) {
    throw new AgenziaArtifactError("download-evidence-invalid");
  }
  if (evidence.byte_length < 1 || evidence.byte_length > MAX_INVOICE_BYTES) {
    throw new AgenziaArtifactError("download-size-unsupported");
  }
  let verifiedPath = evidence.path;
  if (allowedRoot) {
    const [actualRoot, actualPath] = await Promise.all([realpath(allowedRoot), realpath(evidence.path)]);
    const child = relative(actualRoot, actualPath);
    if (!child || child.startsWith("..") || isAbsolute(child)) {
      throw new AgenziaArtifactError("archive-path-outside-run");
    }
    verifiedPath = actualPath;
  }
  const handle = await open(verifiedPath, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0));
  try {
    const before = await handle.stat();
    if (!before.isFile() || before.size !== evidence.byte_length) {
      throw new AgenziaArtifactError("download-file-changed");
    }
    const bytes = await handle.readFile();
    const after = await handle.stat();
    if (after.size !== before.size || after.mtimeMs !== before.mtimeMs || sha256(bytes) !== evidence.sha256) {
      throw new AgenziaArtifactError("download-file-changed");
    }
    return bytes;
  } finally {
    await handle.close();
  }
}

async function writeExact(path, bytes) {
  const result = { path, byte_length: bytes.length, sha256: sha256(bytes) };
  try {
    await writeFile(path, bytes, { flag: "wx", mode: 0o600 });
    return result;
  } catch (error) {
    if (error?.code !== "EEXIST") throw error;
    await readVerifiedFile(result);
    return { ...result, recovered_existing_exact_copy: true };
  }
}

function validateArchiveIdentity({ year, category, documentKey }) {
  if (!/^\d{4}$/.test(String(year))) throw new AgenziaArtifactError("archive-year-invalid");
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(category ?? "")) {
    throw new AgenziaArtifactError("archive-category-invalid");
  }
  if (!/^[a-f0-9]{64}$/.test(documentKey ?? "")) {
    throw new AgenziaArtifactError("archive-document-key-invalid");
  }
}

/** Preserve an XML or P7M original and hash-link any extracted signed XML. */
export async function archiveInvoiceOriginal({ evidence, archiveRoot, year, category, documentKey }) {
  validateArchiveIdentity({ year, category, documentKey });
  const bytes = await readVerifiedFile(evidence);
  const directory = join(archiveRoot, String(year), category, "originals");
  await mkdir(directory, { recursive: true, mode: 0o700 });

  if (isFatturaXml(bytes)) {
    const original = await writeExact(join(directory, `${documentKey}.xml`), bytes);
    return {
      kind: "xml",
      original: { ...original, preservation: "byte_exact_copy" },
      extracted_xml: null,
      signature_validation: "not_applicable"
    };
  }

  const extracted = extractXmlFromP7m(bytes);
  const original = await writeExact(join(directory, `${documentKey}.p7m`), bytes);
  const extractedDirectory = join(archiveRoot, String(year), category, "extracted");
  await mkdir(extractedDirectory, { recursive: true, mode: 0o700 });
  const extractedXml = await writeExact(join(extractedDirectory, `${documentKey}.xml`), extracted);
  return {
    kind: "p7m",
    original: { ...original, preservation: "byte_exact_copy" },
    extracted_xml: {
      ...extractedXml,
      source_p7m_sha256: original.sha256,
      binding: "cms_encapsulated_content"
    },
    signature_validation: "not_performed"
  };
}

/** Verify and archive a PDF saved by the operator through the native print dialog. */
export async function archiveNativePdf({ evidence, archiveRoot, year, category, documentKey }) {
  validateArchiveIdentity({ year, category, documentKey });
  const bytes = await readVerifiedFile(evidence);
  if (bytes.subarray(0, 5).toString("ascii") !== "%PDF-") {
    throw new AgenziaArtifactError("native-output-not-pdf");
  }
  const directory = join(archiveRoot, String(year), category, "pdf");
  await mkdir(directory, { recursive: true, mode: 0o700 });
  const pdf = await writeExact(join(directory, `${documentKey}.pdf`), bytes);
  return {
    ...pdf,
    preservation: "byte_exact_copy",
    evidence_basis: "operator_native_gap_directory_bytes_verified"
  };
}

export async function verifyArchivedArtifact(artifact, { allowedRoot = null } = {}) {
  const evidence = {
    path: artifact?.path,
    byte_length: artifact?.byte_length,
    sha256: artifact?.sha256
  };
  await readVerifiedFile(evidence, { allowedRoot });
  return true;
}

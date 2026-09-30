# Signature and timestamp verification

This adapter verifies existing files. It never signs, timestamps, uploads or
submits a client document. The operator selects an already installed OpenSSL 3
executable explicitly; missing OpenSSL is a blocker for these checks, not a
reason to install software during a case. Python dependencies are declared in
the shared runtime recipe.

`scripts/patent_box_workflow.py --client-engagement <context>
verify-formalities --plan <output/plan.json> --openssl <absolute executable>`
uses `schemas/formalities-plan.schema.json`. The plan selects exact evidence IDs
from that running archive run. Supported formats are DER CMS detached/attached,
PDF detached CMS signatures, and RFC 3161 responses or tokens. For a CMS file,
select both the signature and the expected original document. For a timestamp,
select the actual bytes it timestamps: a timestamp of the unsigned document
does not establish when a later signature existed.

Use `--trusted-roots`, `--crls`, `--intermediates` and `--trust-basis` only for
independently reviewed local trust configuration. A certificate supplied by the
client is not automatically a trust anchor. The result records exact trust-file
hashes and preserves their bytes. No CA, CRL, OCSP, AIA or timestamp network
request is made. Missing trust or revocation evidence remains NOT_TESTED.

CMS integrity, exact-document binding, signer certificate identity, chain/time,
key usage, digest policy and full-chain CRL verification are distinct results.
Professional authorization requires recognized SHA-256/384/512 message digests.
For PDFs, the excluded ByteRange gap must be precisely the signature Contents.
A signature on an earlier revision can retain its integrity result; unsigned
later bytes block current-document acceptance. DocMDP permission assessment,
LT/LTA evidence and embedded signature-time extraction are not implemented.

RFC 3161 checks bind the imprint, TSA signature, chain and timestamping purpose
to the selected file. The stated validation time is explicit. The verified UTC
time can be compared with a separately reviewed deadline using
`compare_deadline`; code does not select the applicable deadline or infer legal
extensions. Separate results are required for signing powers, qualified status,
declaration notice, office-request deadline and statutory conservation.

`formalities_<digest>` contains an immutable review record and readable report.
A PASS on a cryptographic subcheck does not grant penalty protection or turn a
professional control into PASS. The host must cite the actual result and review
its remaining boundaries. An unsupported or incomplete check cannot be replaced
with a filename, visible signature label, hash or unverified assertion.

Implementation references: [OpenSSL CMS](https://docs.openssl.org/3.0/man1/openssl-cms/),
[certificate verification](https://docs.openssl.org/3.0/man1/openssl-verify/),
and [RFC 3161 verification](https://docs.openssl.org/3.0/man1/openssl-ts/).
The technical tests use synthetic certificates and a synthetic TSA. They do
not establish acceptance with an Italian qualified provider or an affected
Windows host.

# Archive JSON on limited output encodings

Four original Windows reports locate `UnicodeEncodeError` at the Archive CLI's
`_emit` function. It writes unescaped Unicode JSON to the host's text stream.
An actual CLI regression reproduces the failure with synthetic Unicode paths
under CP1252 and ASCII; the same operation succeeds under UTF-8.

The CLI now emits ASCII JSON escapes. A JSON decoder receives the exact original
Unicode values, including non-Latin characters and supplementary-plane symbols.
This deterministic representation preserves the JSON contract independently of
the output stream's ability to encode those characters. It does not replace,
drop, transliterate or anonymize any value. Stored documents, ledger formats,
authorization, input seals and professional decisions are unchanged.

The existing local CLI integration covers configuration, client and engagement
creation, readable navigation and ledger recovery under UTF-8, CP1252 and ASCII.
Before the correction the limited encodings fail in `_emit`; after it all three
pass. The focused workflow repeats the test on Windows and Linux.

The shared component is included by Vera and Lucia. Rebuild their native and
upload packages from the same source; the existing privacy declarations retain
their data classes, provider accounts and external boundaries. JSON escaping
does not change what decoded data reaches a model or make processing local-only.

The precise original host codec, original-task availability and input binding
remain unverified until its exact diagnostic reply and retry arrive. Source,
CI, package and deployment evidence never establish recovery of that task.
Marketplace publication is outside this release.

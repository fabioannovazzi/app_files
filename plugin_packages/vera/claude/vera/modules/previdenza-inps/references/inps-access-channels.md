> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# INPS access channels — verified baseline

Research cut-off: **2026-07-16**. Recheck these sources before relying on the channel or eligibility in a real case. This note describes access mechanics; it does not decide a contribution regime or the legal authority of a particular studio.

## Observed from official sources

- INPS publishes REST APIs for its public Open Data catalogue and datasets. These are not an API for a client's individual contribution position: <https://www.inps.it/it/it/dati-e-bilanci/open-data/api-inps.html>.
- INPS provides authenticated access for eligible intermediaries and other legitimately delegated subjects: <https://www.inps.it/it/it/dettaglio-scheda.it.schede-servizio-strumento.schede-servizi.gestione-deleghe-per-aziende-e-intermediari.html>.
- From 15 January 2026, the centralized delegation flow covers Artigiani, Commercianti, and Gestione Separata positions for eligible intermediaries under law 12/1979. The intermediary uses their own credentials and a client-signed delegation; activation is a portal operation owned by the professional, not by Vera: <https://www.inps.it/content/dam/inps-site/it/scorporati/circolari-e-messaggi/2026/01/Circolare_15134/Allegati/16521_Messaggio-numero-104-del-12-01-2026.pdf>.
- The Fascicolo previdenziale explicitly supports consultation, download, and printing of available documentation: <https://www.inps.it/it/it/dettaglio-scheda.it.schede-servizio-strumento.schede-servizi.fascicolo-previdenziale-del-cittadino-50865.fascicolo-previdenziale-del-cittadino.html>. The current Estratto conto page expressly assigns legal value to the certificative extract requested through INPS; do not present the ordinary online view as certificative: <https://www.inps.it/it/it/dettaglio-scheda.it.schede-servizio-strumento.schede-servizi.consultazione-estratto-conto-contributivo-previdenziale-50119.consultazione-estratto-conto-contributivo-previdenziale.html>.
- INPS publishes PDND/ModI and other partner APIs for bounded statutory purposes. The 2026 Estratto Conto Integrato agreement is limited to previdential bodies established under legislative decrees 509/1994 and 103/1996, not a general commercialista API: <https://www.inps.it/it/it/inps-comunica/atti/circolari-messaggi-e-normativa/dettaglio.circolari-e-messaggi.2026.04.messaggio-numero-1247-del-10-04-2026_15235.html>.
- The May 2026 INPS e-service catalogue lists `EstrattoContoIntegrato`, but the catalogue entry alone does not grant a studio production access: <https://www.inps.it/content/dam/inps-site/pdf/dati-analisi-bilanci/Lista_dei_Servizi.pdf>.

## Product decision supported by that evidence

No verified general-purpose API currently authorizes Vera to fetch a client's contribution position for a commercialista. Cowork therefore uses official downloads supplied as local files. The registrar records the declared origin and file hashes without operating the portal. The human user remains responsible for authentication, profile or delegation, and the download itself. Vera never handles credentials, activates a delegation, navigates, submits, or exports browser state, and all substantive conclusions remain draft material for professional review.

## Still unknown until a real run

- the studio actor's actual INPS profile and mandate for the subject;
- whether a newly published e-service covers the exact case and admits the proposed legal entity;
- whether the selected page or export is complete for the period and contribution management in scope.

If any unknown affects authority or completeness, stop at `blocked_decision` or `partial_evidence` rather than implying direct INPS integration.

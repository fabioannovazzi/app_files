# Official-source map

Checked on 2026-07-16. Re-check current pages at run time because chamber
competence, software flows, forms, fees, and guidance can change.

## What each system does

- **SARI** is the public self-care knowledge base for Registro Imprese and
  Comunicazione Unica guidance. It contains chamber-specific search results and
  cards; it is not the filing application.
- **DIRE** is the current InfoCamere environment used to prepare and transmit
  Registro Imprese/Comunicazione Unica practices. This module prepares a draft
  plan only; it does not operate DIRE.
- **Registro Imprese / REA** identify different publicity and economic-record
  effects. Never use the words "position opening" to collapse them into one
  decision.
- **Agenzia Entrate, INPS, INAIL, SUAP**, and where relevant **IVASS/RUI**, are
  separate recipients or registers. A SARI card may display fields for several
  recipients, but the professional must confirm which ones apply to the case.

## Starting points

- SARI public directory:
  `https://supportospecialisticori.infocamere.it/sariWeb/`
- Official description of SARI from Camera di commercio Cremona-Mantova-Pavia:
  `https://www.cmp.camcom.it/registro-imprese/supporto-specialistico-ri-sari`
- InfoCamere tools and DIRE/Comunicazione Unica:
  `https://registroimprese.infocamere.it/web/guest/strumenti`
- Current DIRE specifications should be verified from an institutional chamber
  notice or official InfoCamere documentation. One 2026 institutional notice is:
  `https://www.ptpo.camcom.it/news/comunica/2026/20260320-dire-nuove-specifiche-ministeriali`
- InfoCamere SARI privacy/legal notice:
  `https://informative.infocamere.it/supporto-specialistico`

For insurance intermediaries, also verify current IVASS/RUI sources and the
competent chamber's regulated-activity guidance. A chamber document that
mentions legacy third/fourth insurance-producer groups is evidence for that
document and territory, not an automatic classification of a new case.

## SARI technical boundary

The public frontend currently uses anonymous chamber-specific sessions and
undocumented JSON implementation routes. No supported OpenAPI specification,
version, SLA, or published automation permission was found. Tenant slugs are
volatile and are not ISO province codes.

Default posture:

1. open SARI in a public, read-only browser;
2. select the exact chamber explicitly;
3. search only topical words, with no client identifier;
4. let a person select the relevant result;
5. register minimal metadata and, only when permitted, a user-provided local
   snapshot;
6. use the result as evidence requiring professional applicability review.

The direct `sari_connector.py` route is available only when the studio records
both a case-specific network approval and a separate written-use authorization
from the relevant rights holder. It performs one tenant initialization plus one
search or one selected-card read, never a bulk crawl. It keeps cookies only in
memory and never calls login, contact, support-question, upload, or submission
routes.

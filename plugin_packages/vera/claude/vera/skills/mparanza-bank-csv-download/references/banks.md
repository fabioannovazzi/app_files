> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Banche richieste e punti di ingresso

Source review: 4 November 2026. These are public entry points and known portal
variants, not supported export recipes or an origin allowlist. All five banks
are **awaiting authenticated target-site testing**. Do not infer CSV availability
from a public description of account movements.

| Priority | Bank | Public entry | Variant to establish from the operator's actual access |
| --- | --- | --- | --- |
| 1 | Intesa Sanpaolo | https://www.intesasanpaolo.com/ | Banca online versus Inbiz; the official FAQ directs Inbiz users through BUSINESS and its access area. |
| 2 | UniCredit | https://www.unicredit.it/ | Banca via Internet per Azienda versus the corporate/UniWeb route. A single login may expose several companies. |
| 3 | BNL | https://bnl.it/ | The published business remote-banking guide identifies https://business.bnl.it/; establish the actual contracted portal. |
| 4 | Sella | https://www.sella.it/ | Internet Banking versus Smart Business Sella, including possible CBI services. |
| 5 | BCC | https://www.relaxbanking.it/ | RelaxBanking for the selected BCC and operator profile; do not substitute another BCC platform. |

Follow the actual bank's official entry link and verify its destination before
Autofill. Do not construct login endpoints, reuse a search-engine login URL or
retain query strings/tokens as setup. Normal bank authentication redirects do
not identify the right client; verify the authenticated account separately.

Public source evidence:

- Intesa: https://www.intesasanpaolo.com/content/internetbanking/it/faq/common/faqHome/scenari-di-autenticazione.impresa.html
- UniCredit: https://www.unicredit.it/it/business/servizi-digitali/tutti-i-servizi/online-banking-imprese/banca-via-internet-per-azienda.html
- UniCredit corporate guide: https://online.unicreditcorporate.it/docs/portale/Portale_Corporate-Guida_Operativa.PDF
- BNL business first-access guide: https://business.bnl.it/resources/files/guida-al-primo-accesso.pdf
- Sella access instructions: https://www.sella.it/web/helpcenter/servizi-digitali/i-nostri-servizi-online
- Sella business transition: https://www.sella.it/web/helpcenter/aziende/passaggio-app-sella-ib-a-sbs
- RelaxBanking: https://www.relaxbanking.it/

The user has selected computer use with 1Password, not an API aggregator.
Do not introduce an open-banking subscription, bank API integration or new
Mparanza-hosted banking service into this pilot.

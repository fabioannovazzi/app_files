# Prima del grafico, il significato dei dati

Caso didattico interamente fittizio.

Il dataset fittizio riporta vendite nette: gennaio 40.000 EUR e febbraio 50.000 EUR. Un campo 'Discount' non è presente. Le note della fonte confermano che Sales è già al netto degli sconti, quindi sottrarli ancora sarebbe errato.

| Periodo fittizio | Sales | Nota della fonte |
| --- | --- | --- |
| 2026-01 | 40.000 EUR | Vendite nette |
| 2026-02 | 50.000 EUR | Vendite nette |
| Discount separato | Assente | Già incorporato in Sales |

R1 contiene due mesi; R2 definisce Sales come vendite nette. Il ruolo Discount è assente come misura separata in questo dataset, non un importo pari a zero.

Intake, significato delle metriche e confronto temporale. La lezione non trasforma l'assenza di una misura in zero né attribuisce capacità di Clara a Vera.

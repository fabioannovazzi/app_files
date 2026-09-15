# Insegnare un passaggio ripetibile nel browser

Caso didattico interamente fittizio.

Un portale didattico locale ha una pagina con un elenco di documenti e un pulsante per scaricare un file di prova. Vogliamo ripetere soltanto quel download. Non ci sono credenziali, pagamenti o dati di clienti.

| Elemento del sito fittizio | Evidenza osservabile | Limite |
| --- | --- | --- |
| Pagina elenco | Un documento denominato DEMO-01 | Contenuto sintetico |
| Pulsante Scarica | Download di synthetic-download.txt | Una sola operazione prevista |
| File atteso | Testo identificativo del caso | Va letto e verificato dopo il download |

La procedura deriva dalla pagina di prova e dal file effettivamente scaricato. La presenza di un pulsante non dimostra che il download sia riuscito.

Sito fittizio locale, operazione di sola lettura e download. Non viene simulato l'accesso a un gestionale né resa disponibile una capacità per un sito reale.

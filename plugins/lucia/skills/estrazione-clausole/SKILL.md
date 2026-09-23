---
name: estrazione-clausole
description: Use when Lucia must extract key terms from one legal document into a readable, source-linked table, including parties, term, renewal, termination, amounts, liability, governing law or forum, with missing and ambiguous terms visible.
---

# Estrarre le clausole in una tabella

Leggi integralmente `../revisione-documentale/SKILL.md` e il suo contratto
documentale condiviso. Riusa quel motore con `--workflow revisione-documentale`:
non esiste un secondo estrattore. Il metodo di base deriva dalla revisione
tabellare di Mike; provenienza e licenza sono conservate nella skill riusata.

Questo percorso serve a leggere i termini di un contratto e ritrovarli nel testo.
Non trasformare una richiesta di estrazione in un parere negoziale o in un elenco
di clausole che dovrebbero esserci. Scegli i campi richiesti dal caso. Se l'utente
vuole una scheda generale, considera parti, oggetto, durata, rinnovo, uscita,
importi e termini di pagamento, responsabilità, legge e foro, rimuovendo ciò che
non serve. Usa termini del documento e spiega abbreviazioni ambigue.

Per ogni campo restituisci valore, clausola/ancora, citazione, eventuali condizioni
o eccezioni e incertezza. Esempio di forma, non di dato da riempire:

| Campo | Risultato | Fonte | Condizione o lacuna |
| --- | --- | --- | --- |
| Rinnovo | Il periodo espressamente previsto | Articolo e citazione effettivi | Preavviso/forma della disdetta se presenti |

Un rinnovo non può essere estratto ignorando l'eccezione nel comma seguente.
Distinguere recesso, disdetta e risoluzione; legge e foro sono due campi diversi.
Conserva valuta, unità, periodicità e imponibile/IVA come documentati. Non
calcolare RAL, prezzo annuo o penale totale da un importo privo di base temporale.

Gli allegati o le modifiche forniti restano fonti distinte; spiega quale testo
integra o modifica il dato e con quale prova. Non dichiarare "non previsto" se
una parte del documento o un allegato necessario non è leggibile. Le ancore DOCX
sono paragrafi XML, non numeri di pagina.

Consegna la scheda leggibile in HTML e la tabella Excel tramite il renderer
comune. La scheda ha una sola fonte principale salvo allegati/modifiche
selezionati. Per confrontare molti contratti usa direttamente la revisione
documentale a matrice. Mostra i termini realmente estratti, non un modulo vuoto
con istruzioni per l'avvocato.

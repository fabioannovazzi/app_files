# Connettori di anonimizzazione / Anonymization connectors

Download: https://mparanza.com/static/shared/vera-integrazioni/downloads/anonymization-connectors.zip

## Italiano

Questo download è separato da Vera. Scegli OpenAI Privacy Filter, GLiNER2-PII
Rizzo PII, Lethe o PII-Shield; puoi ripetere l'installazione per un altro motore. Non viene
consigliato un motore rispetto agli altri. Le tre app usano lo stesso connettore
locale, con una configurazione specifica per ciascuna app.

1. Installa Python 3.12, scarica lo ZIP ed estrailo completamente.
2. Sul computer dove usi Codex, Cowork o Antigravity, apri un terminale nella
   cartella estratta ed esegui `python3.12 install.py --setup` su macOS/Linux
   oppure `py -3.12 install.py --setup` su Windows. Sono inclusi anche
   `Install.command` per macOS e `Install.cmd` per Windows.
3. Scegli il motore e le cartelle per originali e copie filtrate. L'installazione
   crea le cartelle mancanti e scarica solo le dipendenze del motore scelto.
   OpenAI e GLiNER2 richiedono diversi GB per modello e PyTorch. Per Rizzo,
   installa e avvia separatamente la sua app ufficiale sullo stesso computer.
4. Il programma indica la cartella del runtime e crea i tre file di collegamento
   descritti sotto. Le impostazioni esistenti delle app non vengono modificate.

**Codex desktop:** apri il file generato `codex-mcp.toml` e aggiungi la sua
sezione a `~/.codex/config.toml` (`%USERPROFILE%\.codex\config.toml` su Windows).
Se esiste già una sezione con lo stesso nome, aggiorna quella sezione senza
duplicarla. Conserva le altre impostazioni. Riavvia il collegamento MCP.

**Claude Cowork desktop:** in Personalizza → Plugin carica il file generato
`cowork-connector.zip`, abilita il plugin e apri una nuova attività locale.
Questo è un plugin opzionale distinto da Vera. Il server MCP del plugin viene
eseguito sul computer: non installare il runtime nel terminale Linux della VM
Cowork. Questo percorso non usa «Aggiungi connettore remoto» e non richiede di
esporre il computer su Internet. Un amministratore può disabilitare i server
MCP locali. Il plugin generato contiene i percorsi della tua installazione:
configuralo di nuovo su un altro computer, invece di condividere quel file.

**Google Antigravity:** apri la configurazione MCP nell'app (MCP Servers →
Manage MCP Servers → View raw config nell'IDE). Aggiungi la voce contenuta in
`antigravity-mcp.json` all'oggetto `mcpServers`, mantenendo gli altri server.
Nelle versioni correnti il file globale è `~/.gemini/config/mcp_config.json`;
puoi usare anche `.agents/mcp_config.json` nel progetto. Aggiorna un'eventuale
voce con lo stesso nome e ricarica i server MCP.

**Verifica in ciascuna app:** chiedi lo stato del motore scelto, poi usa un file
di prova sintetico nella cartella Input. Indica solo il nome relativo, ad esempio
`prova.txt`; non allegare l'originale e non chiederne la lettura. I percorsi
`/sessions/...` della VM Cowork non sono percorsi del computer. Chiedi di salvare
la copia, controllala localmente e solo dopo chiedi di leggere l'artefatto
filtrato. Verifica i conteggi e che l'originale sia invariato.

I nomi degli strumenti sono elencati nella tabella sotto. Se lo stato non è
pronto, controlla l'installazione del modello; per Rizzo, controlla che l'app sia
aperta sulla porta configurata (predefinita 5005). Un test in un'app non prova
il collegamento nelle altre. Le sessioni cloud/web non sono incluse in questo
percorso locale. Un timeout dell'app non conferma l'esito: controlla la cartella
Output prima di riprovare. I limiti di tempo dell'app possono essere inferiori
al limite del connettore; in caso di timeout ripetuti usa documenti più piccoli.

Per Second Brain non c'è un programma da installare in questo ZIP. Usa il
connettore del gestore del tuo archivio e la
[guida Integrazioni](https://mparanza.com/static/shared/vera-integrazioni/index.html?lang=it).

## English

This download is separate from Vera. Choose OpenAI Privacy Filter, GLiNER2-PII
Rizzo PII, Lethe or PII-Shield; rerun setup to add another engine. No engine is ranked or selected
for you. Each engine has one runtime shared by the three desktop apps.

1. Install Python 3.12 and extract the entire download.
2. On the computer running your desktop app, open a terminal in the extracted
   folder and run `python3.12 install.py --setup` on macOS/Linux or
   `py -3.12 install.py --setup` on Windows. The included `Install.command`
   (macOS) and `Install.cmd` (Windows) launch the same guided setup.
3. Choose the engine, original-document folder and filtered-output folder.
   Only the selected engine's dependencies are installed. OpenAI and GLiNER2
   download model weights and PyTorch and require several GB. Rizzo requires
   its separately installed official app, running on the same computer.
4. Setup prints the runtime directory and creates the following connection
   files. It preserves the apps' existing settings.

| Desktop app | Generated file | Connection step |
| --- | --- | --- |
| Codex | `codex-mcp.toml` | Add its section to `~/.codex/config.toml` (Windows: `%USERPROFILE%\.codex\config.toml`), replacing only an existing section of the same name. Restart the MCP connection. |
| Claude Cowork | `cowork-connector.zip` | Install through Customize → Plugins, enable it and open a new local task. This is a separate optional plugin. |
| Google Antigravity | `antigravity-mcp.json` | Merge its server entry into `mcpServers` in the app's raw MCP configuration, preserving other servers, then reload MCP servers. Current global path: `~/.gemini/config/mcp_config.json`; project alternative: `.agents/mcp_config.json`. |

For Cowork, run setup on the host computer, not inside its Linux code-execution
VM. Plugin-bundled local MCP servers run on the host. Do not use the remote
connector URL form or expose the computer to the Internet. An administrator may
disable local MCP servers. The generated Cowork ZIP contains this computer's
runtime and folder paths; regenerate it for another machine rather than sharing
it. This setup targets local desktop sessions, not web/cloud sessions.

## Tools / Strumenti

| Engine / Motore | Status / Stato | Filter / Filtra | Batch | Read filtered artifact / Leggi copia |
| --- | --- | --- | --- | --- |
| OpenAI Privacy Filter | `privacy_filter_status` | `privacy_filter_file` | `privacy_filter_batch` | `privacy_filter_read` |
| GLiNER2-PII | `gliner2_pii_status` | `gliner2_pii_file` | `gliner2_pii_batch` | `gliner2_pii_read` |
| Rizzo PII | `rizzo_pii_status` | `rizzo_pii_file` | `rizzo_pii_batch` | `rizzo_pii_read` |

In each app, check status, filter a synthetic file using its relative filename
inside Input, review the saved `.txt` copy locally, then request the filtered
artifact with the read tool. Do not attach or read the original in chat first.
Cowork VM paths such as `/sessions/...` are not host-native paths. A successful
connection in one app does not verify another. If a host tool call times out,
check Output before retrying; the host may have a shorter limit than the
connector. Use smaller documents if its timeout repeatedly interrupts processing.

TXT, Markdown, DOCX and PDFs with extractable text are supported. Output is plain
text without layout or a restoration dictionary. Detection can miss sensitive
values. Rizzo's own app and network behavior are managed separately. See
[OpenAI details](README.md), [GLiNER2 details](GLINER2.md) and [Rizzo details](RIZZO.md).

## Update and removal / Aggiornamento e rimozione

Rerun the new download's installer for the same engine and runtime to update.
`--configure-only` regenerates connection files for an installed runtime without
downloading dependencies or models. Supply the same `--engine`, `--input-dir`,
`--output-dir` and any custom `--runtime-dir` or `--rizzo-port`.

Disconnect by removing the engine's Codex/Antigravity MCP entry or its Cowork
plugin. Remove the engine runtime separately if desired. Keep your Input and
Output folders; neither is deleted by disconnecting the connector. Rizzo app
removal is managed separately.

## Second Brain

Vera can consult an existing repository through its provider's connected search
and read tools. This ZIP supplies no Second Brain backend or installer. Follow
the [integration guide](https://mparanza.com/static/shared/vera-integrazioni/index.html?lang=en)
and verify an actual search and read in each app/account.

## Host documentation

- [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp)
- [Cowork local plugin servers](https://support.claude.com/en/articles/13837440-use-plugins-in-claude)
- [Cowork host and VM architecture](https://support.claude.com/en/articles/14479288-claude-cowork-architecture-overview)
- [Antigravity MCP](https://antigravity.google/docs/mcp)

## Sessioni reversibili / Reversible sessions (0.5.0)

Sono disponibili anche **Lethe** (`--engine lethe`, [LETHE.md](LETHE.md)) e
**PII-Shield** (`--engine pii-shield`, [PII-SHIELD.md](PII-SHIELD.md)).
PII-Shield richiede Node.js 22+ e i percorsi `--node` e `--npm` (npm-cli.js).
Lethe richiede una revisione locale dell'intero lavoro prima di creare la sessione.

Per questi due motori crea/apri una sessione, riusa lo stesso `session_id` per
ogni documento e ripristina il risultato con quella sessione. Dizionari e valori
originali restano locali. Il ripristino restituisce solo il percorso del file.

The two reversible engines expose session_create/session_open and restore.
File/batch tools require the exact same session_id across the job. The existing
OpenAI, GLiNER2 and Rizzo interfaces remain redaction-only: no session or restore
tool is advertised. Rizzo's desktop UI supports a per-document dictionary, but
its inspected HTTP API offers neither session extension nor a restoration
endpoint. The connector does not manufacture a replacement mapping/restorer.

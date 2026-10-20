# Feed RSS – Commissione VI Finanze (Camera dei deputati)

Due feed per NetNewsWire, aggiornati automaticamente due volte al giorno (lun–sab):

| Feed | Contenuto |
|---|---|
| `interrogazioni.xml` | Una voce per ogni interrogazione 5-xxxxx (a risposta immediata o in commissione), con link all'allegato che contiene il testo della risposta del Governo |
| `sedute.xml` | Una voce per ogni seduta con tutto il resto: sede referente, sede consultiva, atti del Governo, audizioni, Comitato dei nove, commissioni riunite |

I rinvii delle interrogazioni ("Rinvio dell'interrogazione n. 5-…") non vengono segnalati, perché non contengono una risposta.

---

## Messa in funzione (una volta sola, circa 15 minuti)

### 1. Crea l'account GitHub
Vai su <https://github.com/signup> e crea un account gratuito. Il nome utente comparirà nell'indirizzo dei feed (es. `brusaterra`).

### 2. Crea il repository
1. In alto a destra: **+** → **New repository**
2. Repository name: `camera-finanze`
3. Seleziona **Public** (GitHub Pages gratuito richiede un repository pubblico; contiene solo dati pubblici della Camera)
4. Spunta **Add a README file**
5. **Create repository**

### 3. Carica lo script e la pagina
1. Nel repository: **Add file** → **Upload files**
2. Trascina `camera_feed.py`, `README.md` e la cartella **`docs`** (con dentro `index.html`)
3. In basso: **Commit changes**

### 4. Crea il file di automazione
La cartella `.github` inizia con un punto e il Finder del Mac la nasconde, quindi è più semplice crearla a mano:
1. **Add file** → **Create new file**
2. Nel campo del nome scrivi esattamente: `.github/workflows/aggiorna-feed.yml`
   (digitando le barre `/` GitHub crea le cartelle da solo)
3. Incolla il contenuto del file `aggiorna-feed.yml`
4. **Commit changes**

### 5. Avvia la prima esecuzione
1. Tab **Actions** → se compare un pulsante verde per abilitare i workflow, cliccalo
2. A sinistra: **Aggiorna feed Commissione VI Finanze** → **Run workflow** → **Run workflow**
3. Dopo circa un minuto deve comparire un segno di spunta verde.
   Nel repository ora ci sono `docs/interrogazioni.xml` e `docs/sedute.xml`.

### 6. Pubblica i feed
1. Tab **Settings** → a sinistra **Pages**
2. Source: **Deploy from a branch**
3. Branch: **main**, cartella **/docs** → **Save**
4. Dopo uno o due minuti la pagina indica l'indirizzo del sito.

### 7. Aggiungi i feed a NetNewsWire
In NetNewsWire: **File → New Feed** (⌘N) e incolla, sostituendo `NOMEUTENTE`:

```
https://NOMEUTENTE.github.io/camera-finanze/interrogazioni.xml
https://NOMEUTENTE.github.io/camera-finanze/sedute.xml
```

Al primo collegamento compaiono le sedute del mese scorso e di quello in corso; da lì in avanti arrivano solo le novità.

---

## Se qualcosa non va

- **La spunta in Actions è rossa con "Permission denied" / errore 403 su `git push`**
  Settings → Actions → General → *Workflow permissions* → **Read and write permissions** → Save, poi rilancia.
- **La spunta è rossa con "Nessuna pagina letta"**
  Il sito della Camera non ha risposto ai server di GitHub. Se succede una volta è un disservizio momentaneo; se succede sempre, la Camera blocca i server GitHub e conviene far girare lo script sul Mac (si può fare con un'attività programmata del Mac, chiedere a Claude).
- **Email di GitHub "scheduled workflow disabled"**
  Basta riattivarlo dal tab Actions. Lo script salva comunque una modifica al mese proprio per evitarlo.
- **La Camera cambia l'impaginazione della pagina**
  I feed smettono di ricevere voci nuove: serve adeguare `camera_feed.py`.

## Come funziona
`camera_feed.py` legge la pagina della Commissione VI per il mese corrente e quello precedente (`https://www.camera.it/leg19/210?commissione=06&annomese=AAAAMM&view=filtered`), separa le interrogazioni dal resto, conserva lo storico in `docs/stato.json` (così le voci non spariscono quando la pagina passa al mese successivo) e scrive i due feed. Per seguire un'altra commissione basta cambiare `COMMISSIONE = "06"` (es. `"05"` Bilancio).

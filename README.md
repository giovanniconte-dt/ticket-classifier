# Classificatore Ticket AI

Sistema POC per classificazione automatica di ticket usando LangChain e LLM.

## Descrizione

Il classificatore legge ticket non classificati da un database SQL Server, li analizza usando un Agent AI con LangChain, e aggiorna automaticamente il database con la classificazione ("request" o "incident").

## Struttura Progetto

```
classificatore/
├── main.py              # Script principale con logica batch
├── config.py            # Configurazione (DB, LLM, system prompt)
├── tools.py             # Tools LangChain per database
├── requirements.txt     # Dipendenze Python
├── README.md            # Questa documentazione
├── env.example          # Template variabili ambiente (rinominare in .env)
├── request.txt          # Descrizione categoria REQUEST
└── incident.txt         # Descrizione categoria INCIDENT
```

## Prerequisiti

1. **Python 3.8+**
2. **Ollama** installato e in esecuzione (con modello llama3.2:3b o altro)
3. **SQL Server** accessibile
4. **Driver ODBC per SQL Server** installato:
   - Windows: ODBC Driver 17 for SQL Server (o versione successiva)
   - Linux: Installare Microsoft ODBC Driver for SQL Server
   - macOS: Installare Microsoft ODBC Driver for SQL Server

## Installazione

1. **Clona o copia la cartella `classificatore/`**

2. **Installa le dipendenze Python:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configura le variabili ambiente:**
   ```bash
   cp env.example .env
   ```
   Poi modifica `.env` con le tue credenziali (vedi sezione Configurazione).

4. **Verifica che Ollama sia in esecuzione:**
   ```bash
   ollama list
   ```
   Se necessario, scarica il modello:
   ```bash
   ollama pull llama3.2:3b
   ```

## Configurazione

Crea un file `.env` nella cartella `classificatore/` con le seguenti variabili:

### SQL Server

```env
# Metodo 1: Windows Authentication (Trusted Connection)
SQL_SERVER_DRIVER=ODBC Driver 17 for SQL Server
SQL_SERVER=localhost
SQL_DATABASE=nome_database
SQL_TRUSTED_CONNECTION=yes

# Metodo 2: SQL Server Authentication
SQL_SERVER_DRIVER=ODBC Driver 17 for SQL Server
SQL_SERVER=localhost
SQL_DATABASE=nome_database
SQL_USERNAME=tuo_username
SQL_PASSWORD=tua_password
SQL_TRUSTED_CONNECTION=no
```

### LLM (Ollama)

```env
# Modello LLM (default: llama3.2:3b)
LLM_MODEL=llama3.2:3b

# Temperature (0 = deterministico, default: 0)
LLM_TEMPERATURE=0

# Base URL (opzionale, se Ollama non è su localhost:11434)
LLM_BASE_URL=http://localhost:11434
```

## Schema Database

Il sistema si aspetta una tabella `ticket` con la seguente struttura:

```sql
CREATE TABLE ticket (
    Id                 INT IDENTITY PRIMARY KEY,
    Numero             VARCHAR(MAX) NOT NULL,
    Classificazione    VARCHAR(MAX) NOT NULL,
    Categoria          VARCHAR(MAX) NOT NULL,
    Sottocategoria     VARCHAR(MAX) NOT NULL,
    Descrizione        VARCHAR(MAX) NOT NULL,
    Classificazione_AI VARCHAR(MAX)  -- request, incident, NULL
)
```

## Utilizzo

### Esecuzione Base

```bash
cd classificatore
python main.py
```

Lo script:
1. Si connette al database SQL Server
2. Recupera tutti i ticket con `Classificazione_AI IS NULL`
3. Classifica ogni ticket usando l'Agent AI
4. Aggiorna il database con la classificazione
5. Mostra un report finale con statistiche

### Output

Lo script genera:
- **Log su console**: Progresso in tempo reale
- **File `classificatore.log`**: Log completo delle operazioni

Esempio di output:
```
2025-01-XX XX:XX:XX - INFO - Avvio Classificatore Ticket AI
2025-01-XX XX:XX:XX - INFO - ✅ Trovati 10 ticket da classificare
2025-01-XX XX:XX:XX - INFO - [1/10] Processando ticket ID 123
2025-01-XX XX:XX:XX - INFO -   📋 Classificazione: incident
2025-01-XX XX:XX:XX - INFO -   ✅ Ticket ID 123 aggiornato nel database
...
2025-01-XX XX:XX:XX - INFO - REPORT FINALE
2025-01-XX XX:XX:XX - INFO - Ticket totali: 10
2025-01-XX XX:XX:XX - INFO - Ticket classificati: 10
2025-01-XX XX:XX:XX - INFO -   - Request: 3
2025-01-XX XX:XX:XX - INFO -   - Incident: 7
```

## Classificazione

Il sistema classifica i ticket in due categorie:

### REQUEST
Richieste pianificate, desiderate o autorizzate che NON derivano da malfunzionamenti:
- Richieste di accesso e abilitazione
- Richieste di informazione e supporto
- Modifiche standard e pre-approvate
- Richieste di miglioramento e nuove funzionalità
- Azioni pianificate (non emergenziali)

### INCIDENT
Eventi non pianificati che causano interruzione o degrado di servizio:
- Interruzione non pianificata di servizio
- Errori di sistema e codici errore
- Degrado delle prestazioni
- Malfunzionamenti rispetto al comportamento atteso
- Problemi di integrazione e dipendenze

I criteri dettagliati sono definiti nei file `request.txt` e `incident.txt`.

## Sicurezza

- **Parametri preparati**: Tutte le query SQL usano parametri preparati per prevenire SQL injection
- **Validazione input**: La classificazione viene validata prima dell'aggiornamento nel database
- **Credenziali**: Le credenziali del database sono gestite tramite variabili ambiente (file `.env`)

## Troubleshooting

### Errore connessione database

**Problema**: `pyodbc.Error: [Microsoft][ODBC Driver Manager] Data source name not found`

**Soluzione**: 
- Verifica che il driver ODBC sia installato
- Controlla il nome del driver in `.env` (es. "ODBC Driver 17 for SQL Server")
- Su Linux, installa: `sudo apt-get install unixodbc-dev` e il driver Microsoft

### Errore Ollama

**Problema**: `Connection refused` o `Model not found`

**Soluzione**:
- Verifica che Ollama sia in esecuzione: `ollama list`
- Scarica il modello: `ollama pull llama3.2:3b`
- Verifica `LLM_BASE_URL` in `.env` se Ollama non è su localhost:11434

### Classificazione non valida

**Problema**: L'Agent restituisce classificazioni non valide

**Soluzione**:
- Verifica che i file `request.txt` e `incident.txt` siano presenti
- Controlla i log per vedere la risposta dell'Agent
- Considera di affinare il system prompt in `config.py`

## Limitazioni

- **POC**: Questo è un Proof of Concept, non un sistema di produzione
- **Performance**: La classificazione può essere lenta con molti ticket (usa batch processing)
- **Accuratezza**: L'accuratezza dipende dalla qualità del modello LLM e del system prompt
- **Errori**: In caso di errore, il ticket non viene aggiornato (verifica i log)

## Sviluppi Futuri

- [ ] Supporto per batch processing con limiti configurabili
- [ ] Retry automatico per classificazioni fallite
- [ ] Dashboard per monitoraggio classificazioni
- [ ] Supporto per altri database (PostgreSQL, MySQL)
- [ ] Validazione e feedback per migliorare il system prompt

## Licenza

Questo progetto è un POC per scopi didattici.

## Supporto

Per problemi o domande, consulta i log in `classificatore.log` o verifica la configurazione in `.env`.

"""
Configurazione per il Classificatore Ticket AI

Gestisce:
- Connessione SQL Server
- Configurazione LLM
- System prompt per classificazione
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_ollama import ChatOllama

# Carica variabili ambiente
load_dotenv()

# Directory del progetto
PROJECT_DIR = Path(__file__).parent


def load_category_description(filename: str) -> str:
    """Carica il contenuto di un file di descrizione categoria."""
    file_path = PROJECT_DIR / filename
    if not file_path.exists():
        raise FileNotFoundError(f"File {filename} non trovato in {PROJECT_DIR}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def build_system_prompt() -> str:
    """
    Costruisce il system prompt integrando le descrizioni delle categorie.
    
    Returns:
        System prompt completo per l'Agent classificatore
    """
    # Carica descrizioni categorie
    request_desc = load_category_description("request.txt")
    incident_desc = load_category_description("incident.txt")
    
    # Costruisci system prompt
    system_prompt = f"""Sei un classificatore di ticket IT.

Classifica il ticket come:
- "request": Richieste pianificate, non derivanti da malfunzionamenti
- "incident": Eventi non pianificati che causano interruzione o degrado del servizio

Restituisci:
- Prima riga: SOLO "request" o "incident" (lowercase, senza virgolette).
- Seconda riga (opzionale): una breve motivazione (una frase).

Esempio di risposta corretta:
request
Richiesta di accesso a sistema pianificata

---

CRITERI REQUEST:

{request_desc}

---

CRITERI INCIDENT:

{incident_desc}

---

Analizza il ticket, confronta con i criteri e restituisci prima la classificazione, poi (opzionale) la motivazione.

Esempi corretti:
request
Il ticket riguarda una richiesta di abilitazione utente
incident

NON fare:
- "request"
- La classificazione è: request
- REQUEST
    """

    return system_prompt


# Configurazione SQL Server
SQL_SERVER_CONFIG = {
    "driver": os.getenv("SQL_SERVER_DRIVER", "ODBC Driver 17 for SQL Server"),
    "server": os.getenv("SQL_SERVER", ""),
    "database": os.getenv("SQL_DATABASE", ""),
    "username": os.getenv("SQL_USERNAME", ""),
    "password": os.getenv("SQL_PASSWORD", ""),
    "trusted_connection": os.getenv("SQL_TRUSTED_CONNECTION", "no").lower() == "yes",
}


def get_connection_string() -> str:
    """
    Costruisce la connection string per SQL Server.
    
    Returns:
        Connection string formattata per pyodbc
    """
    config = SQL_SERVER_CONFIG
    
    if config["trusted_connection"]:
        # Windows Authentication
        conn_str = (
            f"DRIVER={{{config['driver']}}};"
            f"SERVER={config['server']};"
            f"DATABASE={config['database']};"
            f"Trusted_Connection=yes;"
        )
    else:
        # SQL Server Authentication
        conn_str = (
            f"DRIVER={{{config['driver']}}};"
            f"SERVER={config['server']};"
            f"DATABASE={config['database']};"
            f"UID={config['username']};"
            f"PWD={config['password']};"
        )
    
    return conn_str


# Configurazione LLM
LLM_CONFIG = {
    "model": os.getenv("LLM_MODEL", "llama3.2:3b"),
    "temperature": float(os.getenv("LLM_TEMPERATURE", "0")),
    "base_url": os.getenv("LLM_BASE_URL", None),  # Opzionale, per Ollama custom
}


def get_llm() -> ChatOllama:
    """
    Crea e restituisce l'istanza LLM configurata.
    
    Returns:
        Istanza ChatOllama configurata
    """
    config = LLM_CONFIG
    
    llm_kwargs = {
        "model": config["model"],
        "temperature": config["temperature"],
    }
    
    # Aggiungi base_url solo se specificato
    if config["base_url"]:
        llm_kwargs["base_url"] = config["base_url"]
    
    return ChatOllama(**llm_kwargs)


# System prompt (caricato una volta all'avvio)
SYSTEM_PROMPT = build_system_prompt()

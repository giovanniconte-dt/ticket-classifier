"""
Script principale per classificazione batch di ticket

Esegue:
1. Recupera ticket non classificati dal database
2. Classifica ogni ticket usando Agent LangChain
3. Aggiorna il database con la classificazione
"""

import json
import re
import sys
import logging
from typing import List, Dict, Any, Optional, Tuple
import pyodbc
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate

from config import (
    get_connection_string,
    get_llm,
    SYSTEM_PROMPT,
)
from tools import update_ticket_classification, get_db_connection


# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('classificatore.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def get_unclassified_tickets_from_db(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Recupera ticket non classificati direttamente dal database.
    
    Args:
        limit: Numero massimo di ticket da recuperare (None = tutti)
    
    Returns:
        Lista di dizionari con i dati dei ticket
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT Id, Numero, Soggetto, Descrizione 
            FROM ticket 
            WHERE Classificazione_AI IS NULL
            ORDER BY Id
        """
        
        if limit:
            query += " OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY"
            cursor.execute(query, (limit,))
        else:
            cursor.execute(query)
        
        tickets = []
        for row in cursor.fetchall():
            tickets.append({
                "Id": row[0],
                "Numero": row[1],
                "Soggetto": row[2] or "",
                "Descrizione": row[3]
            })
        
        conn.close()
        return tickets
    
    except Exception as e:
        logger.error(f"Errore nel recupero ticket dal database: {e}")
        raise


MOTIVAZIONE_MAX_LEN = 500


def _extract_json_from_response(response: str) -> Optional[dict]:
    """Estrae un oggetto JSON dalla risposta (utile se l'LLM aggiunge testo extra)."""
    response = response.strip()
    # Prova json.loads diretto
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    # Fallback: estrai da markdown code block (```json ... ```)
    code_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Fallback: estrai primo oggetto JSON (da primo { a ultimo })
    start = response.find('{')
    if start >= 0:
        depth = 0
        for i, c in enumerate(response[start:], start):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(response[start : i + 1])
                    except json.JSONDecodeError:
                        break
    return None


def classify_ticket_description(chain, description: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Classifica una descrizione di ticket usando la chain LangChain.
    
    Args:
        chain: Chain LangChain configurata (prompt | llm)
        description: Testo del ticket (Soggetto + Descrizione) da classificare
    
    Returns:
        Tupla (classificazione, motivazione): classificazione "request"/"incident" o None,
        motivazione breve o None
    """
    try:
        # Prepara il messaggio per la chain
        message = f"Classifica il seguente ticket:\n\n{description}"
        
        # Invoca la chain
        result = chain.invoke({"input": message})
        
        response = result.content.strip()
        if not response:
            logger.warning("Risposta Agent vuota")
            return (None, None)
        
        parsed = _extract_json_from_response(response)
        if not parsed:
            logger.warning(f"Risposta Agent non è JSON valido: '{response[:200]}...'")
            return (None, None)
        
        esito = (parsed.get("esito") or "").strip()
        if isinstance(esito, str):
            esito = esito.lower()
        else:
            esito = str(esito).lower()
        
        if esito not in ["request", "incident"]:
            logger.warning(f"Esito non valido nel JSON: '{esito}'")
            return (None, None)
        
        motivazione = parsed.get("motivazione")
        if motivazione is not None and isinstance(motivazione, str):
            motivazione = motivazione.strip() or None
            if motivazione and len(motivazione) > MOTIVAZIONE_MAX_LEN:
                motivazione = motivazione[:MOTIVAZIONE_MAX_LEN]
        else:
            motivazione = None
        
        return (esito, motivazione)
    
    except Exception as e:
        logger.error(f"Errore nella classificazione: {e}")
        return (None, None)


def update_ticket_in_db(
    ticket_id: int,
    classification: str,
    motivazione: Optional[str] = None,
) -> bool:
    """
    Aggiorna la classificazione di un ticket nel database.
    
    Args:
        ticket_id: ID del ticket
        classification: Classificazione ("request" o "incident")
        motivazione: Motivazione breve (opzionale)
    
    Returns:
        True se aggiornato con successo, False altrimenti
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Validazione
        classification_lower = classification.lower().strip()
        if classification_lower not in ["request", "incident"]:
            logger.error(f"Classificazione non valida: {classification}")
            conn.close()
            return False
        
        # Aggiorna con parametri preparati
        update_query = "UPDATE ticket SET Classificazione_AI = ?, Motivazione_AI = ? WHERE Id = ?"
        cursor.execute(update_query, (classification_lower, motivazione, ticket_id))
        conn.commit()
        
        rows_affected = cursor.rowcount
        conn.close()
        
        return rows_affected > 0
    
    except Exception as e:
        logger.error(f"Errore nell'aggiornamento ticket ID {ticket_id}: {e}")
        return False


def main():
    """Funzione principale per esecuzione batch."""
    logger.info("=" * 60)
    logger.info("Avvio Classificatore Ticket AI")
    logger.info("=" * 60)
    
    try:
        # Inizializza LLM e Agent
        logger.info("Inizializzazione LLM e Agent...")
        llm = get_llm()
        
        # Crea Agent con system prompt (senza tools, solo classificazione)
        # Nota: create_agent può richiedere tools, ma per la classificazione
        # possiamo usare direttamente l'LLM con system prompt
        from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
        
        system_prompt_template = SystemMessagePromptTemplate.from_template(SYSTEM_PROMPT)
        human_prompt_template = HumanMessagePromptTemplate.from_template("{input}")
        
        prompt = ChatPromptTemplate.from_messages([
            system_prompt_template,
            human_prompt_template
        ])
        
        chain = prompt | llm
        
        logger.info("✅ LLM e Agent inizializzati")
        
        # Recupera ticket non classificati
        logger.info("\nRecupero ticket non classificati dal database...")
        tickets = get_unclassified_tickets_from_db()
        
        if not tickets:
            logger.info("✅ Nessun ticket da classificare. Uscita.")
            return
        
        logger.info(f"✅ Trovati {len(tickets)} ticket da classificare\n")
        
        # Statistiche
        stats = {
            "total": len(tickets),
            "classified": 0,
            "request": 0,
            "incident": 0,
            "errors": 0,
        }
        
        # Processa ogni ticket
        for i, ticket in enumerate(tickets, 1):
            ticket_id = ticket["Id"]
            numero = ticket["Numero"]
            soggetto = ticket.get("Soggetto", "") or ""
            descrizione = ticket["Descrizione"]
            
            logger.info(f"[{i}/{len(tickets)}] Processando ticket ID {ticket_id} (Numero: {numero})")
            
            # Costruisci testo per LLM (Soggetto + Descrizione)
            testo_ticket = f"Soggetto: {soggetto}\n\nDescrizione: {descrizione}" if soggetto else descrizione
            
            # Classifica
            classification, motivazione = classify_ticket_description(chain, testo_ticket)
            
            if not classification:
                logger.warning(f"  ⚠️  Impossibile classificare ticket ID {ticket_id}")
                stats["errors"] += 1
                continue
            
            logger.info(f"  📋 Classificazione: {classification}")
            if motivazione:
                logger.info(f"  💬 Motivazione: {motivazione}")
            
            # Aggiorna database
            if update_ticket_in_db(ticket_id, classification, motivazione):
                logger.info(f"  ✅ Ticket ID {ticket_id} aggiornato nel database")
                stats["classified"] += 1
                stats[classification] += 1
            else:
                logger.error(f"  ❌ Errore nell'aggiornamento ticket ID {ticket_id}")
                stats["errors"] += 1
        
        # Report finale
        logger.info("\n" + "=" * 60)
        logger.info("REPORT FINALE")
        logger.info("=" * 60)
        logger.info(f"Ticket totali: {stats['total']}")
        logger.info(f"Ticket classificati: {stats['classified']}")
        logger.info(f"  - Request: {stats['request']}")
        logger.info(f"  - Incident: {stats['incident']}")
        logger.info(f"Errori: {stats['errors']}")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Errore critico nell'esecuzione: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

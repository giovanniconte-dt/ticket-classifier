"""
Script principale per classificazione batch di ticket

Esegue:
1. Recupera ticket non classificati dal database
2. Classifica ogni ticket usando Agent LangChain
3. Aggiorna il database con la classificazione
"""

import sys
import logging
from typing import List, Dict, Any, Optional
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
            SELECT Id, Numero, Descrizione 
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
                "Descrizione": row[2]
            })
        
        conn.close()
        return tickets
    
    except Exception as e:
        logger.error(f"Errore nel recupero ticket dal database: {e}")
        raise


def classify_ticket_description(chain, description: str) -> Optional[str]:
    """
    Classifica una descrizione di ticket usando la chain LangChain.
    
    Args:
        chain: Chain LangChain configurata (prompt | llm)
        description: Descrizione del ticket da classificare
    
    Returns:
        Classificazione ("request" o "incident") o None in caso di errore
    """
    try:
        # Prepara il messaggio per la chain
        message = f"Classifica il seguente ticket:\n\n{description}"
        
        # Invoca la chain
        result = chain.invoke({"input": message})
        
        # Estrai la risposta
        response = result.content.strip().lower()
        
        # Normalizza e valida la risposta
        response_clean = response.replace('"', '').replace("'", "").strip()
        
        if response_clean in ["request", "incident"]:
            return response_clean
        else:
            # Prova a estrarre la classificazione dalla risposta
            if "request" in response_clean:
                return "request"
            elif "incident" in response_clean:
                return "incident"
            else:
                logger.warning(f"Risposta Agent non valida: '{response}'")
                return None
    
    except Exception as e:
        logger.error(f"Errore nella classificazione: {e}")
        return None


def update_ticket_in_db(ticket_id: int, classification: str) -> bool:
    """
    Aggiorna la classificazione di un ticket nel database.
    
    Args:
        ticket_id: ID del ticket
        classification: Classificazione ("request" o "incident")
    
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
        update_query = "UPDATE ticket SET Classificazione_AI = ? WHERE Id = ?"
        cursor.execute(update_query, (classification_lower, ticket_id))
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
            descrizione = ticket["Descrizione"]
            
            logger.info(f"[{i}/{len(tickets)}] Processando ticket ID {ticket_id} (Numero: {numero})")
            
            # Classifica
            classification = classify_ticket_description(chain, descrizione)
            
            if not classification:
                logger.warning(f"  ⚠️  Impossibile classificare ticket ID {ticket_id}")
                stats["errors"] += 1
                continue
            
            logger.info(f"  📋 Classificazione: {classification}")
            
            # Aggiorna database
            if update_ticket_in_db(ticket_id, classification):
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

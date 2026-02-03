"""
Tools LangChain per interagire con il database SQL Server

Tutti i tools usano parametri preparati per prevenire SQL injection.
"""

from langchain_core.tools import tool
import pyodbc
from typing import List, Dict, Any
from config import get_connection_string


def get_db_connection():
    """Crea e restituisce una connessione al database."""
    conn_str = get_connection_string()
    return pyodbc.connect(conn_str)


@tool
def get_unclassified_tickets(limit: int = 100) -> str:
    """
    Recupera i ticket non ancora classificati (Classificazione_AI IS NULL).
    
    Questo tool legge i ticket dal database che non hanno ancora una classificazione AI.
    Restituisce una lista formattata con Id, Numero e Descrizione di ciascun ticket.
    
    Args:
        limit: Numero massimo di ticket da recuperare (default: 100)
    
    Returns:
        Stringa formattata con i ticket non classificati o messaggio di errore
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Query con parametri preparati (SICURO)
        query = """
            SELECT Id, Numero, Descrizione 
            FROM ticket 
            WHERE Classificazione_AI IS NULL
            ORDER BY Id
        """
        
        # Se limit è specificato, aggiungilo alla query
        if limit and limit > 0:
            query += f" OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY"
            cursor.execute(query, (limit,))
        else:
            cursor.execute(query)
        
        tickets = cursor.fetchall()
        conn.close()
        
        if not tickets:
            return "Nessun ticket non classificato trovato nel database."
        
        # Formatta risultati
        result = f"Trovati {len(tickets)} ticket non classificati:\n\n"
        for ticket in tickets:
            ticket_id, numero, descrizione = ticket
            # Tronca descrizione se troppo lunga
            desc_short = descrizione[:100] + "..." if len(descrizione) > 100 else descrizione
            result += f"ID: {ticket_id} | Numero: {numero}\n"
            result += f"Descrizione: {desc_short}\n\n"
        
        return result
    
    except Exception as e:
        return f"Errore nel recupero ticket: {str(e)}"


@tool
def update_ticket_classification(ticket_id: int, classification: str) -> str:
    """
    Aggiorna la classificazione AI di un ticket specifico.
    
    Questo tool aggiorna il campo Classificazione_AI nel database per un ticket specifico.
    La classificazione deve essere "request" o "incident" (case-insensitive).
    
    Args:
        ticket_id: ID del ticket da aggiornare (chiave primaria)
        classification: Classificazione da assegnare ("request" o "incident")
    
    Returns:
        Messaggio di conferma o errore
    """
    try:
        # Validazione classificazione
        classification_lower = classification.lower().strip()
        if classification_lower not in ["request", "incident"]:
            return f"Errore: Classificazione non valida. Deve essere 'request' o 'incident', ricevuto: '{classification}'"
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verifica che il ticket esista
        check_query = "SELECT Id FROM ticket WHERE Id = ?"
        cursor.execute(check_query, (ticket_id,))
        if not cursor.fetchone():
            conn.close()
            return f"Errore: Ticket con ID {ticket_id} non trovato nel database."
        
        # Aggiorna classificazione con parametri preparati (SICURO)
        update_query = "UPDATE ticket SET Classificazione_AI = ? WHERE Id = ?"
        cursor.execute(update_query, (classification_lower, ticket_id))
        conn.commit()
        
        rows_affected = cursor.rowcount
        conn.close()
        
        if rows_affected > 0:
            return f"✅ Ticket ID {ticket_id} classificato come '{classification_lower}' con successo."
        else:
            return f"⚠️ Nessuna riga aggiornata per ticket ID {ticket_id}."
    
    except Exception as e:
        return f"Errore nell'aggiornamento ticket: {str(e)}"


# Lista di tutti i tools disponibili
TOOLS = [
    get_unclassified_tickets,
    update_ticket_classification,
]

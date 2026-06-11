import sqlite3

DB_NAME = "political_intel.db"

def fix_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    print("[*] Reparam baza de date...")

    # Tabelul pentru Agentul 1
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS extracted_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            verbatim_evidence TEXT NOT NULL,
            topic TEXT NOT NULL,
            extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (article_id) REFERENCES raw_articles(id) ON DELETE SET NULL
        );
    """)

    # Tabelul pentru Agentul 2
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historical_anomalies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anomaly_type TEXT NOT NULL,
            target TEXT NOT NULL,
            past_statement TEXT NOT NULL,
            current_statement TEXT NOT NULL,
            contradiction_score REAL NOT NULL,
            analyst_note TEXT NOT NULL,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Tabelul pentru Agentul 3
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS threat_vectors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            threat_type TEXT NOT NULL,
            vulnerable_actor TEXT NOT NULL,
            exploiting_actor TEXT NOT NULL,
            description TEXT NOT NULL,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    conn.close()
    print("[+] Tabelele au fost adaugate cu succes! Poti rula pipeline_agents.py din nou.")

if __name__ == "__main__":
    fix_database()
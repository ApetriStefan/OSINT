#!/usr/bin/env python3
import sqlite3
import json
import requests
import sys
import os
from datetime import datetime

# Configurăm encoding-ul pentru consolă pe Windows
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding='utf-8')

DB_NAME = "political_intel.db"
MODEL_NAME = "gemma-4-e4b"

# --- SCHEME JSON PENTRU STRUCTURED OUTPUT ---

SCHEMA_AGENT_1 = {
    "type": "object",
    "properties": {
        "extracted_events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "actor": {"type": "string"},
                    "action": {"type": "string"},
                    "verbatim_evidence": {"type": "string"},
                    "topic": {"type": "string"}
                },
                "required": ["actor", "action", "verbatim_evidence", "topic"]
            }
        }
    },
    "required": ["extracted_events"]
}

SCHEMA_AGENT_2 = {
    "type": "object",
    "properties": {
        "anomalies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "anomaly_type": {"type": "string"},
                    "target": {"type": "string"},
                    "past_statement": {"type": "string"},
                    "current_statement": {"type": "string"},
                    "contradiction_score": {"type": "number"},
                    "analyst_note": {"type": "string"}
                },
                "required": ["anomaly_type", "target", "past_statement", "current_statement", "contradiction_score", "analyst_note"]
            }
        }
    },
    "required": ["anomalies"]
}

SCHEMA_AGENT_3 = {
    "type": "object",
    "properties": {
        "threat_vectors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "threat_type": {"type": "string"},
                    "vulnerable_actor": {"type": "string"},
                    "exploiting_actor": {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["threat_type", "vulnerable_actor", "exploiting_actor", "description"]
            }
        }
    },
    "required": ["threat_vectors"]
}

# --- FUNCȚII DE UTILITATE ---

def call_ollama_agent(system_prompt, user_prompt, temperature=0.0, top_p=0.1, json_schema=None):
    """Apelează Ollama cu streaming live și configurări stricte per Agent."""
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "stream": True,
        "options": {
            "temperature": temperature,
            "top_p": top_p,
            "num_ctx": 64000  # Context extins
        }
    }
    
    if json_schema:
        payload["format"] = json_schema

    print("\n--- INCEPUT GENERARE AGENT ---")
    full_response = ""
    try:
        response = requests.post(url, json=payload, stream=True, timeout=300)
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line.decode('utf-8'))
                text = chunk.get("message", {}).get("content", "")
                sys.stdout.write(text)
                sys.stdout.flush()
                full_response += text
    except Exception as e:
        print(f"\n[-] Eroare la comunicarea cu modelul: {e}")
    print("\n--- SFARSIT GENERARE AGENT ---\n")
    
    # Curățare automată a block-ului <think> din răspunsul final
    if "</think>" in full_response:
        full_response = full_response.split("</think>")[-1].strip()
        
    return full_response

def get_historical_context(actor):
    """Caută în baza de date declarații trecute ale actorului (RAG Simplificat)."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Căutăm declarații din trecut (excluzând ziua de azi) pentru actorul respectiv
    cursor.execute("""
        SELECT extracted_at, verbatim_evidence 
        FROM extracted_events 
        WHERE actor LIKE ? AND date(extracted_at) < date('now', 'localtime')
        ORDER BY extracted_at DESC LIMIT 5
    """, (f"%{actor}%",))
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    for row in rows:
        history.append({
            "date": row[0],
            "past_statement": row[1]
        })
    return history

def save_events_to_db(events):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    for event in events:
        cursor.execute("""
            INSERT INTO extracted_events (actor, action, verbatim_evidence, topic)
            VALUES (?, ?, ?, ?)
        """, (event.get("actor", ""), event.get("action", ""), event.get("verbatim_evidence", ""), event.get("topic", "")))
    conn.commit()
    conn.close()

def save_anomalies_to_db(anomalies):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    for anom in anomalies:
        cursor.execute("""
            INSERT INTO historical_anomalies (anomaly_type, target, past_statement, current_statement, contradiction_score, analyst_note)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (anom.get("anomaly_type", ""), anom.get("target", ""), anom.get("past_statement", ""), anom.get("current_statement", ""), anom.get("contradiction_score", 0.0), anom.get("analyst_note", "")))
    conn.commit()
    conn.close()

def save_threats_to_db(threats):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    for threat in threats:
        cursor.execute("""
            INSERT INTO threat_vectors (threat_type, vulnerable_actor, exploiting_actor, description)
            VALUES (?, ?, ?, ?)
        """, (threat.get("threat_type", ""), threat.get("vulnerable_actor", ""), threat.get("exploiting_actor", ""), threat.get("description", "")))
    conn.commit()
    conn.close()

# --- EXECUTIA PIPELINE-ULUI ---

if __name__ == "__main__":
    if not os.path.exists("dossier_for_agent_1.txt"):
        print("[-] Fișierul 'dossier_for_agent_1.txt' nu există! Rulează mai întâi scriptul selector.")
        sys.exit(1)

    with open("dossier_for_agent_1.txt", "r", encoding="utf-8") as f:
        dossier_text = f.read()

    print("[*] S-a încărcat dosarul de presă. Inițializare Celulă de Inteligență...\n")

    # ==========================================
    # AGENT 1: OSINT Collector
    # ==========================================
    print("[+] RULARE AGENT 1 (Extragerea Structurată a Entităților)...")
    prompt_sys_1 = (
        "You are an elite OSINT Information Extractor specialized in the Romanian geopolitical, economic, and social landscape. "
        "Your task is to extract key events, declarations, and actions from the provided Romanian dossier. "
        "Extract core political actions, major economic events, national security developments, and severe systemic crises. "
        "RULES: "
        "1. Do not translate the quotes. 'verbatim_evidence' MUST be exactly copy-pasted from the Romanian text. "
        "2. Fields 'actor', 'action', and 'topic' must be written in English. "
        "3. Output ONLY valid JSON matching the schema."
    )
    
    resp_1 = call_ollama_agent(prompt_sys_1, dossier_text, temperature=0.0, top_p=0.1, json_schema=SCHEMA_AGENT_1)
    try:
        events_data = json.loads(resp_1).get("extracted_events", [])
        save_events_to_db(events_data)
        print(f"[*] Agent 1 a extras cu succes {len(events_data)} evenimente unice.")
    except Exception as e:
        print(f"[-] Eroare la parsarea JSON de la Agent 1: {e}")
        events_data = []

    # ==========================================
    # AGENT 2: Fact-Checker & Archivist
    # ==========================================
    print("\n[+] RULARE AGENT 2 (Arhivist & Detectare Contradicții)...")
    all_anomalies = []
    
    for event in events_data:
        actor = event.get("actor", "")
        history = get_historical_context(actor)
        
        # Dacă nu avem istoric pentru acest actor, sărim peste pentru a economisi timp/tokeni
        if not history:
            continue
            
        print(f" -> Verificare istoric pentru: {actor} (Găsite {len(history)} declarații anterioare)")
        
        prompt_sys_2 = (
            "You are an Automated Political Archivist. You will receive TODAY_EVENT and HISTORICAL_CONTEXT for an actor. "
            "Detect contradictions, policy reversals, or strategic silence. Write analysis in English, keep quotes in Romanian. "
            "Calculate a contradiction_score (0.0 to 1.0). If the score is below 0.5, output an empty array []."
        )
        user_msg_2 = json.dumps({"TODAY_EVENT": event, "HISTORICAL_CONTEXT": history}, ensure_ascii=False)
        
        resp_2 = call_ollama_agent(prompt_sys_2, user_msg_2, temperature=0.0, top_p=0.1, json_schema=SCHEMA_AGENT_2)
        try:
            anoms = json.loads(resp_2).get("anomalies", [])
            all_anomalies.extend(anoms)
        except Exception as e:
            print(f"[-] Eroare la parsarea JSON de la Agent 2 pentru {actor}: {e}")

    if all_anomalies:
        save_anomalies_to_db(all_anomalies)
        print(f"[*] Agent 2 a detectat {len(all_anomalies)} contradicții istorice.")
    else:
        print("[*] Agent 2 nu a detectat anomalii majore astăzi (sau nu există istoric suficient).")

    # ==========================================
    # AGENT 3: Red Teamer
    # ==========================================
    print("\n[+] RULARE AGENT 3 (Red Teamer & Identificare Vulnerabilități)...")
    prompt_sys_3 = (
        "You are a ruthless, hostile Political Strategist (Red Teamer). "
        "Analyze the structured JSON data of today's political events and identified contradictions. "
        "Identify 'Threat Vectors': 1. Who is most vulnerable? 2. How can an opposing party weaponize this tomorrow? 3. Is there Parasitic Framing? "
        "Write your analysis strictly in English."
    )
    
    payload_3 = {
        "agent_1_extracted_events": events_data,
        "agent_2_anomalies": all_anomalies
    }
    
    resp_3 = call_ollama_agent(prompt_sys_3, json.dumps(payload_3, ensure_ascii=False), temperature=0.2, top_p=0.5, json_schema=SCHEMA_AGENT_3)
    try:
        threats_data = json.loads(resp_3).get("threat_vectors", [])
        save_threats_to_db(threats_data)
        print(f"[*] Agent 3 a identificat {len(threats_data)} vectori de amenințare strategici.")
    except Exception as e:
        print(f"[-] Eroare la parsarea JSON de la Agent 3: {e}")
        threats_data = []

    # ==========================================
    # AGENT 4: Synthesizer (The Director)
    # ==========================================
    print("\n[+] RULARE AGENT 4 (Sinteza Executivă)...")
    
    payload_4 = {
        "agent_1_extracted_events": events_data,
        "agent_2_anomalies": all_anomalies,
        "agent_3_threat_vectors": threats_data
    }
    
    prompt_sys_4 = (
        "You are a Senior Political Intelligence Analyst specialized in Romanian domestic politics and Open Source Intelligence (OSINT). "
        "Synthesize the raw JSON payload into a highly sophisticated, executive-level political intelligence briefing. "
        "CORE DIRECTIVES:\n"
        "1. SILENCE IS A SIGNAL: Analyze strategic silence or deflections.\n"
        "2. DETECT PARASITIC FRAMING: Differentiate tactical voting from ideological alliances.\n"
        "3. WEAPONIZE CONTRADICTIONS: Highlight hypocrisies provided in anomalies.\n"
        "4. BE UNBIASED AND COLD: Speak in terms of leverage, public perception management, and risk.\n\n"
        "OUTPUT CONSTRAINTS:\n"
        "- Write entirely in ROMANIAN.\n"
        "- Generate exactly 5 predictions in Section 4 with Confidence Scores (e.g., 85%) and Justifications based strictly on raw data.\n\n"
        "USE THIS EXACT MARKDOWN STRUCTURE:\n"
        "# 🇷🇴 Sinteza Politică Locală: [Insert Today's Date]\n\n"
        "## 1. REZUMATUL ZILEI (TL;DR)\n* [3-sentence summary]\n\n"
        "## 2. DINAMICA PUTERII ȘI ALIANȚE SUBTERANE\n* [Analysis of power dynamics, backdoor deals, and tactical behavior]\n\n"
        "## 3. EXPLOATAREA EVENIMENTELOR SOCIALE (Black Swan Tracking)\n* [How tragedies/failures are weaponized]\n\n"
        "## 4. PREDICȚII ȘI ANOMALII PENTRU MÂINE\n"
        "* **Ce urmărim mâine: [Prediction 1]**\n  * *Confidence Score:* [X%]\n  * *Justificare:* [...]\n"
        "* **Ce urmărim mâine: [Prediction 2]**\n  * *Confidence Score:* [X%]\n  * *Justificare:* [...]\n"
        "* **Ce urmărim mâine: [Prediction 3]**\n  * *Confidence Score:* [X%]\n  * *Justificare:* [...]\n"
        "* **Ce urmărim mâine: [Prediction 4]**\n  * *Confidence Score:* [X%]\n  * *Justificare:* [...]\n"
        "* **Ce urmărim mâine: [Prediction 5]**\n  * *Confidence Score:* [X%]\n  * *Justificare:* [...]\n\n"
        "**Nivel de Volatilitate:** [Scăzut / Mediu / Ridicat] - [1-sentence explanation]"
    )
    
    final_markdown = call_ollama_agent(
        prompt_sys_4, 
        json.dumps(payload_4, ensure_ascii=False), 
        temperature=0.0, 
        top_p=0.1, 
        json_schema=None # Agent 4 generează Markdown liber, nu JSON
    )

    # Salvarea rezultatului final
    today_date = datetime.now().strftime('%Y-%m-%d')
    output_filename = f"Sinteza_Politica_{today_date}.md"
    
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(final_markdown)
        
    print(f"\n[+] PROCES COMPLET! Dosarul final a fost generat cu succes: {output_filename}")
#!/usr/bin/env python3
import sqlite3
import json
import requests
import subprocess
import socket
import time
import platform
import sys
import os
import re
import feedparser
from datetime import datetime
from bs4 import BeautifulSoup

# Configurare mediu Windows
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding='utf-8')

DB_NAME = "political_intel.db"
MODEL_NAME = "gemma-4-e4b"

# --- KEYWORDS & SOURCES ---
STRATEGIC_KEYWORDS = [
    "ciolacu", "ciucă", "tomac", "bolojan", "psd", "pnl", "usr", "aur", "udmr", 
    "guvern", "ministru", "premier", "dna", "scandal", "licitație", "fonduri", 
    "pnrr", "nato", "drone", "defecțiune", "anchetă", "csm", "justiție", 
    "corupție", "parlament", "senat", "deputați", "constituțională", 
    "rafila", "grindeanu", "turcan"
]

RSS_FEEDS = {
    "G4Media": "https://www.g4media.ro/feed",
    "HotNews": "https://www.hotnews.ro/feed",
    "Digi24": "https://www.digi24.ro/rss",
    "ActiveNews": "https://www.activenews.ro/rss",
    "B1TV": "https://www.b1tv.ro/feed",
    "Agerpres": "https://www.agerpres.ro/home.rss",
    "Mediafax": "https://www.mediafax.ro/rss"
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# --- DATABASE SETUP ---
def ensure_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raw_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            title TEXT NOT NULL,
            link TEXT UNIQUE NOT NULL,
            summary TEXT,
            published_date TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS extracted_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            verbatim_evidence TEXT NOT NULL,
            topic TEXT NOT NULL,
            extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
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

# --- UTILS & OLLAMA COMMS ---
def get_romanian_date():
    """Returnează data curentă formatată complet în limba română."""
    RO_MONTHS = {
        1: "Ianuarie", 2: "Februarie", 3: "Martie", 4: "Aprilie", 5: "Mai", 6: "Iunie",
        7: "Iulie", 8: "August", 9: "Septembrie", 10: "Octombrie", 11: "Noiembrie", 12: "Decembrie"
    }
    now = datetime.now()
    return f"{now.day} {RO_MONTHS[now.month]} {now.year}"

def clean_html(raw_html):
    if not raw_html: return ""
    clean_regex = re.compile('<.*?>')
    return " ".join(re.sub(clean_regex, '', raw_html).split())

def extract_json_from_text(text):
    if "</think>" in text:
        text = text.split("</think>")[-1].strip()
    elif "<think>" in text:
        text = text.split("<think>")[-1].strip()
        
    match = re.search(r'```(?:json)?\s*(\{.*\}|\[.*\])\s*```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
        
    start_brace = text.find('{')
    start_bracket = text.find('[')
    
    if start_brace != -1 and (start_bracket == -1 or start_brace < start_bracket):
        end_brace = text.rfind('}')
        if end_brace != -1:
            return text[start_brace:end_brace+1].strip()
    elif start_bracket != -1:
        end_bracket = text.rfind(']')
        if end_bracket != -1:
            return text[start_bracket:end_bracket+1].strip()
            
    return text.strip()

def safe_extract_list(parsed_json, expected_key):
    """
    Extrage în mod securizat o listă de obiecte dintr-un JSON parsant.
    Suportă atât formatele directe [ {..}, {..} ], cât și cele împachetate { "key": [..] }.
    """
    if isinstance(parsed_json, list):
        return parsed_json
    if isinstance(parsed_json, dict):
        if expected_key in parsed_json and isinstance(parsed_json[expected_key], list):
            return parsed_json[expected_key]
        for val in parsed_json.values():
            if isinstance(val, list):
                return val
        return [parsed_json]
    return []

def check_ollama_model():
    """Verifică dacă modelul este instalat și accesibil în Ollama."""
    global MODEL_NAME
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            if MODEL_NAME not in models:
                if f"{MODEL_NAME}:latest" in models:
                    MODEL_NAME = f"{MODEL_NAME}:latest"
                else:
                    print(f"\n[!!! EROARE CRITICĂ !!!] Modelul '{MODEL_NAME}' nu există în Ollama!")
                    print(f"Modele instalate pe acest server: {', '.join(models)}")
                    sys.exit(1)
    except Exception as e:
        print(f"[-] Nu s-au putut verifica modelele din Ollama: {e}")

def ensure_ollama_running():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(('localhost', 11434)) == 0:
            check_ollama_model()
            return True
    
    print("[*] Se încearcă pornirea automată a serverului Ollama...")
    try:
        cmd = ["ollama", "serve"]
        if platform.system() == "Windows":
            subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(10):
            time.sleep(2)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('localhost', 11434)) == 0:
                    check_ollama_model()
                    return True
    except Exception as e:
        print(f"[-] Eroare la pornirea automată: {e}")
    return False

def call_ollama(system_prompt, user_prompt, temp=0.0, top_p=0.1, json_mode=False):
    url = "http://localhost:11434/api/chat"
    
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "stream": True,
        "options": {
            "temperature": temp,
            "top_p": top_p,
            "num_ctx": 128000  # Dacă apar erori CUDA tip 500, poți schimba această valoare la 64000
        }
    }

    print("\n--- INCEPUT GENERARE OLLAMA ---")
    full_response = ""
    try:
        response = requests.post(url, json=payload, stream=True, timeout=None)
        
        if response.status_code != 200:
            print(f"\n[!!! EROARE API OLLAMA HTTP {response.status_code} !!!]")
            print(f"Detalii: {response.text}")
            return ""

        for line in response.iter_lines():
            if line:
                chunk = json.loads(line.decode('utf-8'))
                if "error" in chunk:
                    print(f"\n[!!! EROARE INTERNĂ OLLAMA !!!]: {chunk['error']}")
                    return ""
                
                text = chunk.get("message", {}).get("content", "")
                sys.stdout.write(text)
                sys.stdout.flush()
                full_response += text
    except Exception as e:
        print(f"\n[-] Eroare de rețea cu Ollama: {e}")
        
    print("\n--- SFARSIT GENERARE OLLAMA ---\n")
    return extract_json_from_text(full_response) if json_mode else full_response

def scrape_full_text(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        if response.status_code != 200: return None
        soup = BeautifulSoup(response.text, "html.parser")
        paragraphs = soup.find_all("p")
        cleaned_paragraphs = [p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 25]
        return "\n\n".join(cleaned_paragraphs)[:6000]
    except Exception:
        return None

def get_historical_context(actor):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT extracted_at, verbatim_evidence 
        FROM extracted_events 
        WHERE actor LIKE ? 
        AND date(extracted_at) < date('now', 'localtime') 
        ORDER BY extracted_at DESC LIMIT 5
    """, (f"%{actor}%",))
    rows = cursor.fetchall()
    conn.close()
    return [{"date": row[0], "past_statement": row[1]} for row in rows]

# ==========================================
# ETAPA 1: Preluare articole brute din RSS
# ==========================================
def run_rss_ingestion():
    print("\n[+] ETAPA 1: Extragere RSS...")
    conn = sqlite3.connect(DB_NAME)
    new_count = 0
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        cursor = conn.cursor()
        for source, url in RSS_FEEDS.items():
            try:
                response = requests.get(url, headers=HEADERS, timeout=15, verify=False)
                if response.status_code != 200: 
                    print(f" -> {source}: EROARE HTTP {response.status_code}")
                    continue
                
                feed = feedparser.parse(response.content)
                for entry in feed.entries:
                    link = entry.get("link", "").strip()
                    if not link: continue
                    
                    cursor.execute("SELECT 1 FROM raw_articles WHERE link = ?", (link,))
                    if cursor.fetchone() is not None: continue
                    
                    title = entry.get("title", "No Title").strip()
                    summary = clean_html(entry.get("summary", entry.get("description", "")))
                    published = datetime.now().strftime("%Y-%m-%d")

                    cursor.execute("""
                        INSERT OR IGNORE INTO raw_articles (source_name, title, link, summary, published_date)
                        VALUES (?, ?, ?, ?, ?)
                    """, (source, title, link, summary, published))
                    if cursor.rowcount > 0: new_count += 1
                print(f" -> {source}: Actualizat")
            except Exception as e:
                print(f" -> {source}: EROARE ({e})")
        conn.commit()
    finally:
        conn.close()
    print(f"[*] S-au adăugat {new_count} articole noi azi.")

# ==========================================
# ETAPA 2: Selectorul și generarea dosarului
# ==========================================
def run_selector_and_dossier():
    print("\n[+] ETAPA 2: Selectare OSINT și Generare Dosar Presă...")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today_str = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("""
        SELECT id, source_name, title, summary, link 
        FROM raw_articles 
        WHERE date(scraped_at, 'localtime') = ? OR published_date = ?
        ORDER BY id DESC
    """, (today_str, today_str))
    db_articles = cursor.fetchall()
    conn.close()

    if not db_articles:
        print("[-] Nu există știri. Se oprește execuția.")
        sys.exit(1)

    selection_input = []
    for a in db_articles:
        title_lower = a[2].lower()
        summary_lower = (a[3] or "").lower()
        is_strat = any(kw in title_lower or kw in summary_lower for kw in STRATEGIC_KEYWORDS)
        
        selection_input.append({
            "title": f"{'[STRATEGIC SIGNAL] ' if is_strat else ''}{a[2]}",
            "source": a[1],
            "summary": (a[3][:100] + "...") if a[3] else "",
            "link": a[4],
            "is_strategic": is_strat
        })

    selection_input = sorted(selection_input, key=lambda x: x["is_strategic"], reverse=True)
    print(f"[*] {len(selection_input)} articole trimise către analiza de relevanță.")

    system_prompt_1 = (
        "You are a Senior Intelligence Director. Analyze the following list of raw daily news articles from Romania, in it's entirety. "
        "Select EXACTLY 10 articles (after analyzing and justifying your choice for each one!) that represent the highest strategic importance: DOMESTIC POLITICS, MACROECONOMY, NATIONAL SECURITY, or SEVERE SYSTEMIC CRISES, AS WELL AS 1 OR 2 BIG NEWS FROM OTHER SUBJECTS THAT ARE OF NATIONAL IMPORTANCE. "
        "CRITICAL RULES: "
        "1. You MUST completely IGNORE and FILTER OUT any articles about: Reality TV shows, showbiz, weather forecasts, sports, minor accidents, or generic international news that doesn't involve Romania. "
        "2. Prioritize articles marked with [STRATEGIC SIGNAL] as they contain highly relevant domestic intelligence elements. "
        "Output your selection STRICTLY as a JSON array containing objects with keys: 'title', 'link', 'source'. Do not wrap the JSON output in markdown formatting unless necessary, and if you must use reasoning, put your reasoning inside <think> tags first."
    )
    
    raw_json = call_ollama(system_prompt_1, f"Identify top news: {json.dumps(selection_input)}", temp=0.0, top_p=0.1, json_mode=True)
    
    selected_list = []
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            selected_list = safe_extract_list(parsed, "selected_articles")
        except Exception as e:
            print(f"[-] Eșec parsare JSON Selector: {e}")
            
    if not selected_list or not isinstance(selected_list, list) or len(selected_list) == 0:
        print("[!] Activare Fallback Absolut: Preiau primele 10 articole.")
        selected_list = selection_input[:10]
    elif len(selected_list) > 10:
        selected_list = selected_list[:10]
    elif len(selected_list) < 10:
        links_deja_alese = {item.get("link") for item in selected_list}
        necesar = 10 - len(selected_list)
        pentru_umplere = [a for a in selection_input if a["link"] not in links_deja_alese][:necesar]
        selected_list.extend(pentru_umplere)

    scraped_data_package = []
    for idx, item in enumerate(selected_list):
        title = item.get("title", "No Title").replace("[STRATEGIC SIGNAL] ", "")
        print(f" -> Descărcare text ({idx+1}/{len(selected_list)}): {title[:40]}...")
        full_text = scrape_full_text(item.get("link", ""))
        if full_text:
            scraped_data_package.append({"title": title, "source": item.get("source", ""), "full_text": full_text})

    if not scraped_data_package:
        print("[-] Nu s-au putut descărca textele surselor. Oprim execuția.")
        sys.exit(1)

    today_ro = get_romanian_date()

    system_prompt_2 = (
        "You are a Master OSINT Journalist and Analyst. Read the full scraped text of the selected news articles "
        "and generate a comprehensive, highly detailed news summary dossier in Romanian.\n\n"
        "You MUST strictly follow this exact plain-text format for each article, separating them with double newlines:\n\n"
        "ȘTIREA [Number]: [CLEAN TITLE HERE - DO NOT BOLD, DO NOT USE # OR ANY MARKDOWN AT ALL]\n"
        "[Write a comprehensive, deep, and highly informative narrative summary in Romanian. This summary must "
        "preserve the political context, key figures, critical facts, and include direct verbatim Romanian quotes from "
        "the provided text. Keep it strictly professional, objective, and analytical. Write at least 2-3 detailed paragraphs for each story to ensure deep coverage.]\n"
        f"(Sursa: [Source Name] - {today_ro})\n\n"
        "CRITICAL FORMAT RULES:\n"
        "1. Do not use any markdown headers (such as #, ##, ###) or bold any words inside the title line or text.\n"
        "2. Do not write any conversational intros or outros. Start directly with 'ȘTIREA 1:'.\n"
        "3. Keep Romanian quotes completely verbatim."
    )
    
    print("\n[*] Generare Dosar Consolidat...")
    dossier_text = call_ollama(system_prompt_2, json.dumps(scraped_data_package), temp=0.0, top_p=0.1, json_mode=False)
    
    if not dossier_text:
        print("[-] EROARE: Dosarul generat este gol. Oprim execuția agenților.")
        sys.exit(1)
        
    with open("dossier_for_agent_1.txt", "w", encoding="utf-8") as f:
        f.write(dossier_text)
    
    return dossier_text

# ==========================================
# ETAPA 3: AGENT PIPELINE
# ==========================================
def run_agents(dossier_text):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # --- AGENT 1: Extractor ---
    print("\n[+] RULARE AGENT 1 (Extragerea Structurată a Entităților)...")
    prompt_sys_1 = (
        "You are an elite OSINT Information Extractor specialized in the Romanian geopolitical, economic, and social landscape. "
        "Your task is to extract key events, declarations, and actions that have the potential to influence political dynamics, "
        "national security, economic stability, public policy, or public sentiment in Romania.\n"
        "You must extract:\n"
        "1. Core political actions, claims, and declarations by politicians or parties.\n"
        "2. Major economic, financial, and regulatory events.\n"
        "3. National security, defense, and border developments.\n"
        "4. Significant social, humanitarian, or systemic crises.\n"
        "RULES:\n"
        "1. Do not translate the quotes. The 'verbatim_evidence' MUST be an exact, copy-pasted substring from the Romanian text.\n"
        "2. All other fields (topic, action, actor) must be written in English.\n"
        "3. If no event is present, output an empty array [].\n"
        "4. Output ONLY valid JSON matching the schema. Put your reasoning inside <think> tags first, then output the final JSON structure."
    )
    
    resp_1 = call_ollama(prompt_sys_1, f"DOSSIER TEXT:\n{dossier_text}", temp=0.0, top_p=0.1, json_mode=True)
    events_data = []
    if resp_1:
        try:
            parsed_1 = json.loads(resp_1)
            events_data = safe_extract_list(parsed_1, "extracted_events")
            
            for ev in events_data:
                actor = ev.get("actor") or "Unknown Actor"
                action = ev.get("action") or "No Action"
                verbatim = ev.get("verbatim_evidence") or ""
                topic = ev.get("topic") or "General"
                
                cursor.execute("""
                    INSERT INTO extracted_events (actor, action, verbatim_evidence, topic)
                    VALUES (?, ?, ?, ?)
                """, (actor, action, verbatim, topic))
            conn.commit()
            print(f"[*] S-au salvat {len(events_data)} evenimente extrase de Agentul 1.")
        except Exception as e:
            print(f"[-] Eroare parsare Agent 1: {e}")

    # --- AGENT 2: Fact-Checker / Archivist ---
    print("\n[+] RULARE AGENT 2 (Arhivist & Detectare Contradicții)...")
    all_anomalies = []
    if events_data:
        for ev in events_data:
            actor = ev.get("actor", "")
            history = get_historical_context(actor)
            if not history:
                print(f" -> Fără istoric pentru: {actor}")
                continue
                
            print(f" -> Verificare istoric pentru: {actor} (Găsite {len(history)} declarații anterioare)")
            prompt_sys_2 = (
                "You are an Automated Political Archivist. You will receive:\n"
                "1. 'TODAY_EVENT': A JSON object of a claim made today.\n"
                "2. 'HISTORICAL_CONTEXT': A JSON array of past statements made by the same actor.\n"
                "Your job is to detect contradictions, policy reversals, or strategic silence. Write your analysis in English, but keep quotes in Romanian.\n"
                "RULES:\n"
                "1. Calculate a 'contradiction_score' from 0.0 to 1.0.\n"
                "2. If the score is below 0.5, output an empty JSON array []. Do not flag minor things.\n"
                "3. Output ONLY valid JSON matching the schema. Put your reasoning inside <think> tags first, then output the final JSON structure."
            )
            user_msg_2 = json.dumps({"TODAY_EVENT": ev, "HISTORICAL_CONTEXT": history})
            resp_2 = call_ollama(prompt_sys_2, user_msg_2, temp=0.0, top_p=0.1, json_mode=True)
            
            if resp_2:
                try:
                    parsed_2 = json.loads(resp_2)
                    anoms = safe_extract_list(parsed_2, "anomalies")
                    
                    for anom in anoms:
                        anomaly_type = anom.get("anomaly_type") or "Unknown Anomaly"
                        target = anom.get("target") or actor
                        past = anom.get("past_statement") or ""
                        current = anom.get("current_statement") or ""
                        score = float(anom.get("contradiction_score") or 0.0)
                        note = anom.get("analyst_note") or ""
                        
                        cursor.execute("""
                            INSERT INTO historical_anomalies (anomaly_type, target, past_statement, current_statement, contradiction_score, analyst_note)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (anomaly_type, target, past, current, score, note))
                    conn.commit()
                    all_anomalies.extend(anoms)
                except Exception as e:
                    print(f"[-] Eroare parsare Agent 2 pentru {actor}: {e}")

    # --- AGENT 3: Red Teamer ---
    print("\n[+] RULARE AGENT 3 (Red Teamer)...")
    threats_data = []
    if events_data:
        prompt_sys_3 = (
            "You are a ruthless, hostile Political Strategist (Red Teamer). \n"
            "You will receive the structured JSON data of today's political events and identified contradictions.\n"
            "Your job is to identify 'Threat Vectors'. Look at the data and determine:\n"
            "1. Who is most vulnerable right now?\n"
            "2. How can an opposing party weaponize these events tomorrow?\n"
            "3. Is anyone using 'Parasitic Framing' (hijacking another party's narrative)?\n"
            "Write your analysis strictly in English. Output ONLY valid JSON matching the schema. Put your reasoning inside <think> tags first, then output the final JSON structure."
        )
        payload_3 = json.dumps({"agent_1_extracted_events": events_data, "agent_2_anomalies": all_anomalies})
        resp_3 = call_ollama(prompt_sys_3, payload_3, temp=0.2, top_p=0.5, json_mode=True)
        
        if resp_3:
            try:
                parsed_3 = json.loads(resp_3)
                threats_data = safe_extract_list(parsed_3, "threat_vectors")
                
                for t in threats_data:
                    threat_type = t.get("threat_type") or "Unknown Threat"
                    vuln = t.get("vulnerable_actor") or "Unknown Vulnerable"
                    exploit = t.get("exploiting_actor") or "Unknown Exploiting"
                    desc = t.get("description") or ""
                    
                    cursor.execute("""
                        INSERT INTO threat_vectors (threat_type, vulnerable_actor, exploiting_actor, description)
                        VALUES (?, ?, ?, ?)
                    """, (threat_type, vuln, exploit, desc))
                conn.commit()
            except Exception as e:
                print(f"[-] Eroare parsare Agent 3: {e}")

    # --- AGENT 4: Director / Synthesizer ---
    print("\n[+] RULARE AGENT 4 (Sinteza Executivă)...")
    if events_data:
        today_ro = get_romanian_date()

        prompt_sys_4 = (
            "You are a Senior Political Intelligence Analyst specialized in Romanian domestic politics and Open Source Intelligence (OSINT). "
            "Synthesize raw daily data into an executive-level political intelligence briefing.\n\n"
            "CORE ANALYTICAL DIRECTIVES:\n"
            "1. SILENCE IS A SIGNAL: If a major political actor is unusually silent about a major crisis involving their rivals, analyze this as strategic silence (e.g., negotiation leverage or backdoor deals), not as insignificance.\n"
            "2. DETECT PARASITIC FRAMING: Do not mistake tactical voting for ideological alliances. If two opposing parties vote together, verify if one party is parazitizing the other's initiative to push their own narrative.\n"
            "3. WEAPONIZE CONTRADICTIONS: Look at historical quotes provided in the anomalies. Highlight when a politician's current defense directly violates their past statements.\n"
            "4. BE UNBIASED AND COLD: Write with absolute objectivity. Avoid emotional language. Speak in terms of leverage, public perception management, risk, and political survival.\n"
            "5. TACTICAL VS. IDEOLOGICAL CONVERGENCE: Do not mistake separate, convergent tactical behaviors for coordinated subterranean alliances. If opposing parties act similarly (e.g., both rejecting a candidate), frame it as 'convergent strategic interests' or 'parallel opposition' rather than a coordinated secret coalition, unless there is concrete supporting evidence. Always treat backdoor deals described by rivals (e.g., USR's accusations against PSD-AUR) as strategic narratives or weaponized framing, not as objective organizational facts.\n\n"
            "OUTPUT CONSTRAINTS:\n"
            "- Write entirely in ROMANIAN.\n"
            "- Follow exactly the Markdown structure provided below.\n"
            "- Generate exactly 5 predictions with numerical Confidence Scores.\n"
            "- If you must use reasoning first, do so inside <think> tags, then structure the rest strictly as Markdown.\n\n"
            f"# 🇷🇴 Sinteza Politică Locală: {today_ro}\n\n"
            "## 1. REZUMATUL ZILEI (TL;DR)\n* [3-sentence summary]\n\n"
            "## 2. DINAMICA PUTERII ȘI ALIANȚE SUBTERANE\n* [Power dynamics analysis]\n\n"
            "## 3. EXPLOATAREA EVENIMENTELOR SOCIALE\n* [Social exploitation analysis]\n\n"
            "## 4. PREDICȚII ȘI ANOMALII PENTRU MÂINE\n"
            "* **Ce urmărim mâine: [Prediction Title]**\n  * *Confidence Score:* [X%]\n  * *Justificare:* [Text]\n"
            "(Generate exactly 5 such predictions)\n\n"
            "**Nivel de Volatilitate:** [Scăzut / Mediu / Ridicat] - [1-sentence explanation]"
        )
        
        payload_4 = json.dumps({
            "agent_1_extracted_events": events_data,
            "agent_2_anomalies": all_anomalies,
            "agent_3_threat_vectors": threats_data
        })
        
        final_briefing = call_ollama(prompt_sys_4, payload_4, temp=0.0, top_p=0.1, json_mode=False)
        
        # --- AGENT 5: Grammar & Style Corrector ---
        if final_briefing:
            print("\n[+] RULARE AGENT 5 (Corector de Limba Română)...")
            prompt_sys_5 = (
                "You are an elite proofreader and copyeditor specialized in the Romanian language. "
                "Your sole task is to identify and correct any spelling, diacritics, grammar, syntax, or punctuation mistakes in the provided Romanian text. "
                "CRITICAL RULES:\n"
                "1. Do not alter, add, or remove any information, predictions, or intelligence analysis.\n"
                "2. Preserve the exact Markdown structure (#, ##, *, bold text, etc.) of the original document.\n"
                "3. Correct common scraped/scanned typos (e.g., 'ășirii' to 'țării', 'ěmi' to 'îmi', 'aparbine' to 'aparține', 'tehnocratele' to 'tehnocrate ale') and ensure natural Romanian flow.\n"
                "4. Return ONLY the finalized, corrected Romanian Markdown text. No conversational intros or outros."
            )
            
            corrected_briefing = call_ollama(prompt_sys_5, final_briefing, temp=0.0, top_p=0.1, json_mode=False)
            
            today_date = datetime.now().strftime('%Y-%m-%d')
            output_filename = f"Sinteza_Politica_{today_date}.md"
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write(corrected_briefing)
                
            print(f"\n[+] GATA! Dosarul final a fost corectat din punct de vedere gramatical și salvat cu succes: {output_filename}")
        else:
            print("[-] Agent 4 anulat, nu s-a putut genera briefingul.")
    else:
        print("[-] Agent 4 anulat, nu a primit date structurate.")

    conn.close()

if __name__ == "__main__":
    print("==================================================")
    print("      🇷🇴 INIȚIALIZARE PIPELINE OSINT COMPLET      ")
    print("==================================================")
    ensure_database()
    if not ensure_ollama_running():
        sys.exit(1)
        
    run_rss_ingestion()
    dossier = run_selector_and_dossier()
    run_agents(dossier)
#!/usr/bin/env python3
import sqlite3
import json
import sys
from datetime import datetime

# Configurăm codificarea stdout pentru consolele Windows
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding='utf-8')

DB_NAME = "political_intel.db"
OUTPUT_FILE = "pre_fix_payload.json"

def get_unfiltered_articles_today():
    """Extrage toate articolele din baza de date pentru ziua de astăzi fără nicio limitare."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    print(f"[*] Interogare DB pentru data de astăzi: {today_str}")
    
    # Selectăm absolut toate articolele adăugate sau publicate astăzi, fără clauză LIMIT sau echilibrare
    cursor.execute("""
        SELECT id, source_name, title, summary, link, published_date, scraped_at 
        FROM raw_articles 
        WHERE date(scraped_at, 'localtime') = ? OR published_date = ?
        ORDER BY id DESC
    """, (today_str, today_str))
    rows = cursor.fetchall()
    
    # Fallback de siguranță la toate articolele din DB dacă nu s-au făcut adăugiri astăzi
    if not rows:
        print("[!] Nicio știre găsită în DB pentru data de astăzi.")
        print("[*] Se activează fallback-ul: se încarcă toate articolele existente în DB.")
        cursor.execute("""
            SELECT id, source_name, title, summary, link, published_date, scraped_at 
            FROM raw_articles 
            ORDER BY id DESC
        """)
        rows = cursor.fetchall()
        
    conn.close()
    
    articles = []
    for row in rows:
        articles.append({
            "id": row[0],
            "source_name": row[1],
            "title": row[2],
            "summary": row[3],
            "link": row[4],
            "published_date": row[5],
            "scraped_at": row[6]
        })
    return articles

if __name__ == "__main__":
    articles = get_unfiltered_articles_today()
    if not articles:
        print("[-] Baza de date este complet goală.")
        sys.exit(1)
        
    print(f"[+] S-au extras în total {len(articles)} articole brute.")

    # Generăm pachetul exact trimis către Gemma înainte de fix, limitând rezumatul la 100 de caractere
    selection_input = []
    source_distribution = {}
    
    for a in articles:
        src = a["source_name"]
        short_summary = a["summary"][:100] + "..." if a["summary"] else "No summary available"
        selection_input.append({
            "title": a["title"],
            "source": src,
            "summary": short_summary,
            "link": a["link"]
        })
        # Înregistrăm distribuția surselor pentru raport
        source_distribution[src] = source_distribution.get(src, 0) + 1

    # Statistici de distribuție în consolă
    print("\n[*] Distribuția articolelor pe surse în acest pachet brut:")
    for src, count in source_distribution.items():
        print(f"    - {src}: {count} articole")

    # Serializare și salvare în format JSON ordonat (pretty print)
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(selection_input, f, indent=4, ensure_ascii=False)
        print(f"\n[+] Succes! Pachetul complet ({len(selection_input)} intrări) a fost salvat în: {OUTPUT_FILE}")
        print("[*] Poți deschide acest fișier pentru a analiza structura exactă trimisă inițial către Gemma.")
    except Exception as e:
        print(f"[-] Eroare la salvarea fișierului: {e}")
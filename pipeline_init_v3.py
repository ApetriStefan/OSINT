#!/usr/bin/env python3
import sqlite3
import feedparser
import requests
import re
from datetime import datetime
import sys
import time
from email.utils import parsedate_to_datetime

# Configure stdout encoding to prevent UnicodeEncodeError on Windows console
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding='utf-8')

DB_NAME = "political_intel.db"

# Fluxuri RSS funcționale și stabile
RSS_FEEDS = {
    "G4Media": "https://www.g4media.ro/feed",
    "HotNews": "https://www.hotnews.ro/feed",
    "Digi24": "https://www.digi24.ro/rss",
    "B1TV": "https://www.b1tv.ro/feed",
    "Agerpres": "https://www.agerpres.ro/home.rss",
    "Mediafax": "https://www.mediafax.ro/rss"
}

# Configurare User-Agent pentru a nu fi blocați de firewall-urile site-urilor
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def clean_html(raw_html):
    """Elimină tagurile HTML de bază din descrierile feed-ului folosind regex."""
    if not raw_html:
        return ""
    clean_regex = re.compile('<.*?>')
    clean_text = re.sub(clean_regex, '', raw_html)
    return " ".join(clean_text.split())

def init_database():
    """Inițializează baza de date locală cu un try-finally block robust."""
    conn = sqlite3.connect(DB_NAME)
    try:
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
        conn.commit()
    finally:
        conn.close()

def is_article_new(cursor, link):
    """Verifică dacă articolul există deja în baza de date locală."""
    cursor.execute("SELECT 1 FROM raw_articles WHERE link = ?", (link,))
    return cursor.fetchone() is None

def fetch_rss_sources():
    print("[*] Scanare surse RSS...")
    conn = sqlite3.connect(DB_NAME)
    new_count = 0
    
    try:
        cursor = conn.cursor()
        for source, url in RSS_FEEDS.items():
            try:
                # Descărcare prin requests pentru a asigura folosirea headerelor de siguranță
                response = requests.get(url, headers=HEADERS, timeout=10)
                if response.status_code != 200:
                    print(f" -> {source}: EROARE (Status HTTP {response.status_code})")
                    continue
                
                feed = feedparser.parse(response.content)
                for entry in feed.entries:
                    title = entry.get("title", "No Title").strip()
                    link = entry.get("link", "").strip()
                    
                    if not link:
                        continue
                    
                    if not is_article_new(cursor, link):
                        continue
                    
                    summary = clean_html(entry.get("summary", entry.get("description", "")))
                    
                    # Parsare robustă a datei publicării (suportă RSS și standarde Atom)
                    published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
                    if published_parsed:
                        published = time.strftime("%Y-%m-%d", published_parsed)
                    else:
                        published_str = entry.get("published") or entry.get("updated") or ""
                        match = re.search(r'\d{4}-\d{2}-\d{2}', published_str)
                        if match:
                            published = match.group(0)
                        else:
                            try:
                                dt = parsedate_to_datetime(published_str)
                                published = dt.strftime("%Y-%m-%d")
                            except Exception:
                                published = datetime.now().strftime("%Y-%m-%d")

                    cursor.execute("""
                        INSERT OR IGNORE INTO raw_articles (source_name, title, link, summary, published_date)
                        VALUES (?, ?, ?, ?, ?)
                    """, (source, title, link, summary, published))
                    if cursor.rowcount > 0:
                        new_count += 1
                print(f" -> {source}: OK")
            except Exception as e:
                print(f" -> {source}: EROARE ({str(e)})")
        conn.commit()
    finally:
        conn.close()
        
    return new_count

if __name__ == "__main__":
    init_database()
    total_new = fetch_rss_sources()
    print(f"\n[+] Succes! S-au salvat {total_new} articole noi în baza de date locală.")
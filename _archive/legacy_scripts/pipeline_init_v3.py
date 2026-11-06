#!/usr/bin/env python3
import sqlite3
import feedparser
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import sys
import time

# Prevenim erorile de codare pe Windows
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding='utf-8')

DB_NAME = "political_intel.db"

RSS_FEEDS = {
    "G4Media": "https://www.g4media.ro/feed",
    "HotNews": "https://www.hotnews.ro/feed",
    "Digi24": "https://www.digi24.ro/rss",
    "ActiveNews": "https://www.activenews.ro/rss",
    "B1TV": "https://www.b1tv.ro/feed",
    "Agerpres": "https://www.agerpres.ro/home.rss",
    "Mediafax": "https://www.mediafax.ro/rss"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def clean_html(raw_html):
    if not raw_html:
        return ""
    clean_regex = re.compile('<.*?>')
    clean_text = re.sub(clean_regex, '', raw_html)
    return " ".join(clean_text.split())

def init_database():
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

def get_article_published_date(url, default_date):
    """Accesează pagina articolului pentru a extrage data reală din metadatele HTML."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            meta_date = (
                soup.find("meta", property="article:published_time") or 
                soup.find("meta", name="publish-date") or 
                soup.find("meta", property="og:pubdate") or
                soup.find("meta", itemprop="datePublished") or 
                soup.find("meta", name="pubdate")
            )
            if meta_date:
                content = meta_date.get("content", meta_date.get("value", ""))
                match = re.search(r'\d{4}-\d{2}-\d{2}', content)
                if match:
                    return match.group(0)

            time_tag = soup.find("time", datetime=True)
            if time_tag:
                match = re.search(r'\d{4}-\d{2}-\d{2}', time_tag["datetime"])
                if match:
                    return match.group(0)
    except Exception:
        pass
    return default_date

def is_article_new(cursor, link):
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
                response = requests.get(url, headers=HEADERS, timeout=15)
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
                    published = datetime.now().strftime("%Y-%m-%d")
                    
                    # Aici apărea eroarea 'time' is not defined
                    published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
                    if published_parsed:
                        published = time.strftime("%Y-%m-%d", published_parsed)
                    else:
                        published_str = entry.get("published") or entry.get("updated") or ""
                        match = re.search(r'\d{4}-\d{2}-\d{2}', published_str)
                        if match:
                            published = match.group(0)

                    cursor.execute("""
                        INSERT OR IGNORE INTO raw_articles (source_name, title, link, summary, published_date)
                        VALUES (?, ?, ?, ?, ?)
                    """, (source, title, link, summary, published))
                    if cursor.rowcount > 0:
                        new_count += 1
                print(f" -> {source}: OK")
            except requests.exceptions.ReadTimeout:
                print(f" -> {source}: EROARE (Timeout: Serverul a răspuns prea greu)")
            except Exception as e:
                print(f" -> {source}: EROARE ({str(e)})")
        conn.commit()
    finally:
        conn.close()
    return new_count

if __name__ == "__main__":
    init_database()
    total_new = fetch_rss_sources()
    print(f"\n[+] Succes! S-au salvat {total_new} articole brute în baza de date locală.")
#!/usr/bin/env python3
import feedparser
import requests
import json
import re
import sys

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding='utf-8')

OUTPUT_FILE = "pre_fix_payload.json"

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

def fetch_rss_to_json():
    print("[*] Scanare surse RSS și salvare directă în format JSON...")
    articles = []
    source_distribution = {}

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
                
                summary = clean_html(entry.get("summary", entry.get("description", "")))
                short_summary = summary[:100] + "..." if summary else "No summary available"
                
                articles.append({
                    "title": title,
                    "source": source,
                    "summary": short_summary,
                    "link": link
                })
                source_distribution[source] = source_distribution.get(source, 0) + 1
            print(f" -> {source}: OK")
            
        except requests.exceptions.ReadTimeout:
            print(f" -> {source}: EROARE (Timeout)")
        except Exception as e:
            print(f" -> {source}: EROARE ({str(e)})")

    print("\n[*] Distribuția articolelor pe surse extrase astăzi:")
    for src, count in source_distribution.items():
        print(f"    - {src}: {count} articole")

    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(articles, f, indent=4, ensure_ascii=False)
        print(f"\n[+] Succes! Pachetul complet RSS-to-JSON ({len(articles)} intrări) a fost salvat în: {OUTPUT_FILE}")
    except Exception as e:
        print(f"[-] Eroare la salvarea fișierului: {e}")

if __name__ == "__main__":
    fetch_rss_to_json()
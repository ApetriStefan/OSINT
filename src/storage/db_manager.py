"""Database management module with SQLite WAL mode, foreign keys, and indexes."""

import csv
import io
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Generator, List, Optional, Dict, Any

from src.config import get_settings
from src.models.article import RawArticle
from src.models.intelligence import ExtractedEvent, HistoricalAnomaly, ThreatVector
from src.utils_date import get_bucharest_now, get_bucharest_today_str


class DBManager:
    """Manages SQLite operations with WAL mode, robust indexing, and schema migrations."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or get_settings().db_path
        self.init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provide a contextual database connection configured with WAL and foreign keys."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def get_readonly_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provide a strictly read-only SQLite connection using URI mode=ro."""
        abs_path = os.path.abspath(self.db_path).replace("\\", "/")
        uri = f"file:{abs_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self) -> None:
        """Initialize database schema, tables, indexes, and run migrations if necessary."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Raw Articles Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS raw_articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    link TEXT UNIQUE NOT NULL,
                    summary TEXT,
                    published_at TEXT,
                    published_date TEXT,
                    is_date_estimated INTEGER DEFAULT 0,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Run safe column migrations for raw_articles
            cursor.execute("PRAGMA table_info(raw_articles);")
            existing_raw_cols = {row["name"] for row in cursor.fetchall()}
            if "published_at" not in existing_raw_cols:
                cursor.execute("ALTER TABLE raw_articles ADD COLUMN published_at TEXT;")
            if "is_date_estimated" not in existing_raw_cols:
                cursor.execute("ALTER TABLE raw_articles ADD COLUMN is_date_estimated INTEGER DEFAULT 0;")

            # 2. Extracted Events Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS extracted_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER,
                    actor TEXT NOT NULL,
                    canonical_actor TEXT,
                    action TEXT NOT NULL,
                    verbatim_evidence TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    event_hash TEXT,
                    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (article_id) REFERENCES raw_articles(id) ON DELETE SET NULL
                );
            """)

            # Run safe column migrations for extracted_events
            cursor.execute("PRAGMA table_info(extracted_events);")
            existing_cols = {row["name"] for row in cursor.fetchall()}
            if "event_hash" not in existing_cols:
                cursor.execute("ALTER TABLE extracted_events ADD COLUMN event_hash TEXT;")
            if "article_id" not in existing_cols:
                cursor.execute("ALTER TABLE extracted_events ADD COLUMN article_id INTEGER;")
            if "canonical_actor" not in existing_cols:
                cursor.execute("ALTER TABLE extracted_events ADD COLUMN canonical_actor TEXT;")

            # 3. Historical Anomalies Table
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

            # 4. Threat Vectors Table
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

            # 5. Pipeline Executions (State Machine / Tracking)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pipeline_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT UNIQUE NOT NULL,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 6. Performance & Integrity Indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_articles_date ON raw_articles(published_date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_articles_pub_date ON raw_articles(published_date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_articles_scraped ON raw_articles(scraped_at);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_extracted_events_actor ON extracted_events(actor);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_actor ON extracted_events(actor, extracted_at);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_extracted_events_canonical ON extracted_events(canonical_actor);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_extracted_events_date ON extracted_events(extracted_at);")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_extracted_events_hash ON extracted_events(event_hash) WHERE event_hash IS NOT NULL;")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_executions_run ON pipeline_executions(run_id);")

    # ==================== Raw Articles ====================

    def insert_raw_article(self, article: RawArticle) -> bool:
        """Insert a single raw article, ignoring duplicates by link."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO raw_articles 
                (source_name, title, link, summary, published_at, published_date, is_date_estimated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                article.source_name,
                article.title,
                article.link,
                article.summary,
                article.published_at,
                article.published_date,
                1 if article.is_date_estimated else 0
            ))
            return cursor.rowcount > 0

    def insert_raw_articles(self, articles: List[RawArticle]) -> int:
        """Bulk insert raw articles using executemany, returning the number of newly added rows."""
        if not articles:
            return 0
        params = [
            (
                article.source_name,
                article.title,
                article.link,
                article.summary,
                article.published_at,
                article.published_date,
                1 if article.is_date_estimated else 0
            )
            for article in articles
        ]
        with self.get_connection() as conn:
            cursor = conn.cursor()
            before_changes = conn.total_changes
            cursor.executemany("""
                INSERT OR IGNORE INTO raw_articles 
                (source_name, title, link, summary, published_at, published_date, is_date_estimated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, params)
            return conn.total_changes - before_changes

    def get_raw_articles_for_date(self, target_date: str) -> List[RawArticle]:
        """Retrieve raw articles matching publication date (YYYY-MM-DD in Europe/Bucharest)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, source_name, title, link, summary, published_at, published_date, is_date_estimated, scraped_at
                FROM raw_articles
                WHERE published_date = ?
                ORDER BY id DESC
            """, (target_date,))
            rows = cursor.fetchall()
            return [
                RawArticle(
                    id=row["id"],
                    source_name=row["source_name"],
                    title=row["title"],
                    link=row["link"],
                    summary=row["summary"],
                    published_at=row["published_at"],
                    published_date=row["published_date"],
                    is_date_estimated=bool(row["is_date_estimated"]),
                    scraped_at=datetime.fromisoformat(str(row["scraped_at"])) if row["scraped_at"] else None
                )
                for row in rows
            ]

    def get_recent_articles(self, days: int = 1) -> List[RawArticle]:
        """Retrieve articles from the last N days relative to Europe/Bucharest today."""
        cutoff = (get_bucharest_now() - timedelta(days=days)).strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, source_name, title, link, summary, published_at, published_date, is_date_estimated, scraped_at
                FROM raw_articles
                WHERE published_date >= ?
                ORDER BY id DESC
            """, (cutoff,))
            rows = cursor.fetchall()
            return [
                RawArticle(
                    id=row["id"],
                    source_name=row["source_name"],
                    title=row["title"],
                    link=row["link"],
                    summary=row["summary"],
                    published_at=row["published_at"],
                    published_date=row["published_date"],
                    is_date_estimated=bool(row["is_date_estimated"]),
                    scraped_at=datetime.fromisoformat(str(row["scraped_at"])) if row["scraped_at"] else None
                )
                for row in rows
            ]

    # ==================== Extracted Events ====================

    def insert_extracted_event(self, event: ExtractedEvent) -> bool:
        """Insert an extracted event, ignoring duplicates via event_hash."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO extracted_events 
                (article_id, actor, canonical_actor, action, verbatim_evidence, topic, event_hash, extracted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
            """, (
                event.article_id,
                event.actor,
                event.canonical_actor or event.actor,
                event.action,
                event.verbatim_evidence,
                event.topic,
                event.event_hash,
                str(event.extracted_at) if event.extracted_at else None
            ))
            return cursor.rowcount > 0

    def insert_extracted_events(self, events: List[ExtractedEvent]) -> int:
        """Insert multiple extracted events using executemany, ignoring duplicates."""
        if not events:
            return 0
        params = [
            (
                event.article_id,
                event.actor,
                event.canonical_actor or event.actor,
                event.action,
                event.verbatim_evidence,
                event.topic,
                event.event_hash,
                str(event.extracted_at) if event.extracted_at else None
            )
            for event in events
        ]
        with self.get_connection() as conn:
            cursor = conn.cursor()
            before_changes = conn.total_changes
            cursor.executemany("""
                INSERT OR IGNORE INTO extracted_events 
                (article_id, actor, canonical_actor, action, verbatim_evidence, topic, event_hash, extracted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
            """, params)
            return conn.total_changes - before_changes

    def get_actor_history(
        self,
        actor: str,
        limit: int = 5,
        before_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve past statements and evidence for an actor prior to a given date."""
        target_date = before_date or datetime.now().strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT extracted_at, verbatim_evidence, action, topic, canonical_actor
                FROM extracted_events
                WHERE (actor LIKE ? OR canonical_actor LIKE ?)
                  AND date(extracted_at, 'localtime') < ?
                ORDER BY extracted_at DESC
                LIMIT ?
            """, (f"%{actor}%", f"%{actor}%", target_date, limit))
            rows = cursor.fetchall()
            return [
                {
                    "date": str(row["extracted_at"]),
                    "past_statement": row["verbatim_evidence"],
                    "action": row["action"],
                    "topic": row["topic"],
                    "canonical_actor": row["canonical_actor"]
                }
                for row in rows
            ]

    # ==================== Historical Anomalies ====================

    def insert_historical_anomaly(self, anomaly: HistoricalAnomaly) -> bool:
        """Insert a detected anomaly or contradiction."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO historical_anomalies 
                (anomaly_type, target, past_statement, current_statement, contradiction_score, analyst_note)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                anomaly.anomaly_type,
                anomaly.target,
                anomaly.past_statement,
                anomaly.current_statement,
                anomaly.contradiction_score,
                anomaly.analyst_note
            ))
            return cursor.rowcount > 0

    def insert_historical_anomalies(self, anomalies: List[HistoricalAnomaly]) -> int:
        """Bulk insert anomalies."""
        count = 0
        for anom in anomalies:
            if self.insert_historical_anomaly(anom):
                count += 1
        return count

    # ==================== Threat Vectors ====================

    def insert_threat_vector(self, threat: ThreatVector) -> bool:
        """Insert a detected threat vector."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO threat_vectors (threat_type, vulnerable_actor, exploiting_actor, description)
                VALUES (?, ?, ?, ?)
            """, (
                threat.threat_type,
                threat.vulnerable_actor,
                threat.exploiting_actor,
                threat.description
            ))
            return cursor.rowcount > 0

    def insert_threat_vectors(self, threats: List[ThreatVector]) -> int:
        """Bulk insert threat vectors."""
        count = 0
        for threat in threats:
            if self.insert_threat_vector(threat):
                count += 1
        return count

    # ==================== Pipeline Executions / State Machine ====================

    def record_pipeline_execution(
        self,
        run_id: str,
        stage: str,
        status: str,
        details: Optional[str] = None
    ) -> None:
        """Record or update a pipeline execution stage status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO pipeline_executions (run_id, stage, status, details, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(run_id) DO UPDATE SET
                    stage = excluded.stage,
                    status = excluded.status,
                    details = excluded.details,
                    updated_at = CURRENT_TIMESTAMP
            """, (run_id, stage, status, details))

    def get_pipeline_status(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve execution state for a given pipeline run ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT run_id, stage, status, details, created_at, updated_at
                FROM pipeline_executions
                WHERE run_id = ?
            """, (run_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "run_id": row["run_id"],
                "stage": row["stage"],
                "status": row["status"],
                "details": row["details"],
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"])
            }

    # ==================== Dashboard & Monitoring Queries ====================

    def get_dashboard_stats(self) -> Dict[str, int]:
        """Aggregate high-level metrics for dashboard cards."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) AS total FROM raw_articles;")
            articles_count = cursor.fetchone()["total"]

            cursor.execute("SELECT count(*) AS total FROM extracted_events;")
            events_count = cursor.fetchone()["total"]

            cursor.execute("SELECT count(*) AS total FROM historical_anomalies;")
            anomalies_count = cursor.fetchone()["total"]

            cursor.execute("SELECT count(*) AS total FROM threat_vectors;")
            threats_count = cursor.fetchone()["total"]

            cursor.execute("SELECT count(*) AS total FROM pipeline_executions;")
            executions_count = cursor.fetchone()["total"]

            return {
                "total_articles": articles_count,
                "total_events": events_count,
                "total_anomalies": anomalies_count,
                "total_threats": threats_count,
                "total_executions": executions_count,
            }

    def get_latest_anomalies(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent historical anomalies for contradiction tracking."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, anomaly_type, target, past_statement, current_statement,
                       contradiction_score, analyst_note, detected_at
                FROM historical_anomalies
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_latest_threats(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent threat vectors for security monitoring."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, threat_type, vulnerable_actor, exploiting_actor, description, detected_at
                FROM threat_vectors
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_latest_articles(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Retrieve recent raw articles for live feed inspection."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, link, source_name AS source, published_date, scraped_at
                FROM raw_articles
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_latest_executions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve recent pipeline execution runs."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT run_id, stage, status, details, created_at, updated_at
                FROM pipeline_executions
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    # ==================== Database Viewer Read-Only APIs ====================

    def _get_table_schema_dict(self, conn: sqlite3.Connection) -> Dict[str, List[Dict[str, Any]]]:
        """Inspect and return whitelisted table schemas from sqlite_master."""
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row["name"] for row in cursor.fetchall()]
        schema: Dict[str, List[Dict[str, Any]]] = {}
        for t in tables:
            cursor.execute(f"PRAGMA table_info({t});")
            cols = [
                {"name": r["name"], "type": r["type"], "pk": bool(r["pk"])}
                for r in cursor.fetchall()
            ]
            schema[t] = cols
        return schema

    def get_db_tables(self) -> List[Dict[str, Any]]:
        """List all database tables, their row counts, and column metadata (read-only)."""
        with self.get_readonly_connection() as conn:
            schemas = self._get_table_schema_dict(conn)
            result = []
            cursor = conn.cursor()
            for table_name, columns in schemas.items():
                cursor.execute(f"SELECT count(*) AS total FROM {table_name};")
                cnt = cursor.fetchone()["total"]
                result.append({
                    "name": table_name,
                    "row_count": cnt,
                    "columns": columns
                })
            return result

    def get_table_rows(
        self,
        table: str,
        limit: int = 50,
        offset: int = 0,
        sort: Optional[str] = None,
        order: str = "DESC",
        q: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """Safely fetch paginated, sorted, filtered rows from a whitelisted table (read-only)."""
        with self.get_readonly_connection() as conn:
            schemas = self._get_table_schema_dict(conn)
            if table not in schemas:
                raise ValueError(f"Table '{table}' does not exist in database.")

            col_defs = schemas[table]
            valid_cols = [c["name"] for c in col_defs]

            # Enforce max limit of 500
            safe_limit = max(1, min(int(limit), 500))
            safe_offset = max(0, int(offset))
            safe_order = "ASC" if str(order).upper() == "ASC" else "DESC"

            # Determine sort column
            if sort and sort in valid_cols:
                sort_col = sort
            else:
                pk_col = next((c["name"] for c in col_defs if c["pk"]), valid_cols[0] if valid_cols else "rowid")
                sort_col = pk_col

            where_clauses: List[str] = []
            params: List[Any] = []

            # 1. Search text query across string columns
            if q and str(q).strip():
                clean_q = str(q).strip()
                searchable_cols = [
                    c["name"] for c in col_defs
                    if any(t in c["type"].upper() for t in ["TEXT", "CHAR", "VARCHAR", "CLOB"])
                ]
                if not searchable_cols:
                    searchable_cols = valid_cols

                sub_clauses = [f"{c} LIKE ?" for c in searchable_cols]
                where_clauses.append(f"({' OR '.join(sub_clauses)})")
                params.extend([f"%{clean_q}%"] * len(searchable_cols))

            # 2. Date range filtering
            preferred_date_col = next(
                (c for c in ["published_date", "extracted_at", "detected_at", "created_at", "scraped_at"] if c in valid_cols),
                None
            )
            if preferred_date_col:
                if date_from and date_from.strip():
                    where_clauses.append(f"date({preferred_date_col}) >= ?")
                    params.append(date_from.strip())
                if date_to and date_to.strip():
                    where_clauses.append(f"date({preferred_date_col}) <= ?")
                    params.append(date_to.strip())

            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            cursor = conn.cursor()
            # Total count query
            count_sql = f"SELECT count(*) AS total FROM {table} {where_sql};"
            cursor.execute(count_sql, params)
            total_count = cursor.fetchone()["total"]

            # Paginated data query
            data_sql = f"SELECT * FROM {table} {where_sql} ORDER BY {sort_col} {safe_order} LIMIT ? OFFSET ?;"
            cursor.execute(data_sql, params + [safe_limit, safe_offset])
            rows = [dict(r) for r in cursor.fetchall()]

            return {
                "columns": valid_cols,
                "rows": rows,
                "total": total_count,
                "limit": safe_limit,
                "offset": safe_offset,
                "sort": sort_col,
                "order": safe_order
            }

    def get_table_row(self, table: str, row_id: Any) -> Optional[Dict[str, Any]]:
        """Fetch a single row by primary key from a whitelisted table (read-only)."""
        with self.get_readonly_connection() as conn:
            schemas = self._get_table_schema_dict(conn)
            if table not in schemas:
                raise ValueError(f"Table '{table}' does not exist in database.")

            col_defs = schemas[table]
            pk_col = next((c["name"] for c in col_defs if c["pk"]), "id")

            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {table} WHERE {pk_col} = ?;", (row_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def export_table_csv(self, table: str) -> str:
        """Export all rows from a whitelisted table as a CSV string (read-only)."""
        with self.get_readonly_connection() as conn:
            schemas = self._get_table_schema_dict(conn)
            if table not in schemas:
                raise ValueError(f"Table '{table}' does not exist in database.")

            col_defs = schemas[table]
            fieldnames = [c["name"] for c in col_defs]

            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {table};")
            rows = cursor.fetchall()

            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                writer.writerow(dict(r))
            return output.getvalue()

    def get_schema_summary(self) -> Dict[str, Any]:
        """Return a structured summary of database schema and tables (read-only)."""
        with self.get_readonly_connection() as conn:
            schemas = self._get_table_schema_dict(conn)
            cursor = conn.cursor()
            summary: Dict[str, Any] = {}
            for t, cols in schemas.items():
                cursor.execute(f"SELECT count(*) AS total FROM {t};")
                count = cursor.fetchone()["total"]
                summary[t] = {
                    "columns": cols,
                    "row_count": count
                }
            return summary

    def purge_all_data(self) -> Dict[str, int]:
        """Purge all records from all database tables, reset sequences, and run VACUUM."""
        counts: Dict[str, int] = {}
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Respect foreign keys: delete child/dependent tables first
            tables = [
                "threat_vectors",
                "historical_anomalies",
                "extracted_events",
                "raw_articles",
                "pipeline_executions",
            ]
            for table in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table};")
                    row = cursor.fetchone()
                    counts[table] = row[0] if row else 0
                    cursor.execute(f"DELETE FROM {table};")
                except Exception:
                    counts[table] = 0

            # Reset autoincrement sequence counters if sqlite_sequence exists
            try:
                cursor.execute("DELETE FROM sqlite_sequence;")
            except Exception:
                pass

        # Reclaim disk space
        try:
            with self.get_connection() as conn:
                conn.execute("VACUUM;")
        except Exception:
            pass

        return counts


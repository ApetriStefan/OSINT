"""Configuration module for the Romanian OSINT system.

Preserves critical context window settings (num_ctx=131072) and provides
centralized, validated configuration through Pydantic BaseSettings.
"""

from functools import lru_cache
from typing import Dict
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Ollama Settings
    ollama_base_url: str = Field(default="http://localhost:11434", description="Base URL for Ollama API")
    ollama_model: str = Field(default="gemma-4-e4b", description="LLM model name")
    ollama_embed_model: str = Field(default="nomic-embed-text", description="Embedding model name (dim=768)")
    
    # CRITICAL USER REQUIREMENT: Context window must always be 131072 to avoid context truncation
    num_ctx: int = Field(default=131072, description="Context window size in tokens")
    
    temperature: float = Field(default=0.0, description="Sampling temperature for deterministic extraction")
    top_p: float = Field(default=0.1, description="Top-p nucleus sampling parameter")

    # Storage Paths
    db_path: str = Field(default="political_intel.db", description="Path to SQLite database file")
    chroma_path: str = Field(default="chroma_db", description="Directory path for ChromaDB vector store")

    # Ingestion & Scraping Settings
    request_timeout: int = Field(default=15, description="HTTP request timeout in seconds")
    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        description="User-Agent string for HTTP requests"
    )
    max_selected_articles: int = Field(default=10, description="Target number of articles for daily dossier")

    # Default RSS Sources for Romanian Media
    rss_feeds: Dict[str, str] = Field(
        default_factory=lambda: {
            "G4Media": "https://www.g4media.ro/feed",
            "HotNews": "https://www.hotnews.ro/feed",
            "Digi24": "https://www.digi24.ro/rss",
            "ActiveNews": "https://www.activenews.ro/rss",
            "B1TV": "https://www.b1tv.ro/feed",
            "Agerpres": "https://www.agerpres.ro/home.rss",
            "Mediafax": "https://www.mediafax.ro/rss"
        },
        description="Dictionary mapping source name to RSS feed URL"
    )


@lru_cache()
def get_settings() -> Settings:
    """Return a cached instance of application settings."""
    return Settings()

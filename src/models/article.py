"""Article-related Pydantic data models."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl


class RawArticle(BaseModel):
    """Raw article metadata extracted from RSS feeds."""

    id: Optional[int] = Field(default=None, description="Database record ID")
    source_name: str = Field(..., description="Name of the news publication / source")
    title: str = Field(..., description="Headline of the article")
    link: str = Field(..., description="Canonical URL of the article")
    summary: Optional[str] = Field(default="", description="Snippet or brief description")
    published_at: Optional[str] = Field(default=None, description="ISO-8601 UTC timestamp")
    published_date: Optional[str] = Field(default=None, description="Publication date in Europe/Bucharest (YYYY-MM-DD)")
    is_date_estimated: bool = Field(default=False, description="Flag indicating if publication date was estimated or missing")
    scraped_at: Optional[datetime] = Field(default=None, description="Timestamp when article was scraped")


class ScrapedArticle(BaseModel):
    """Full-text scraped article ready for deep processing."""

    title: str = Field(..., description="Cleaned article title")
    source: str = Field(..., description="Source publication")
    link: str = Field(..., description="Original article link")
    full_text: str = Field(..., description="Extracted body text of the article")
    published_at: Optional[str] = Field(default=None, description="ISO-8601 UTC timestamp")
    published_date: Optional[str] = Field(default=None, description="Publication date in Europe/Bucharest (YYYY-MM-DD)")


class SelectedArticle(BaseModel):
    """Article selected for strategic intelligence value."""

    title: str = Field(..., description="Article title (without signal tags)")
    source: str = Field(..., description="Source publication")
    link: str = Field(..., description="Original article link")
    summary: Optional[str] = Field(default="", description="Article summary")
    is_strategic: bool = Field(default=False, description="Flag indicating strategic relevance")
    score: float = Field(default=0.0, description="Taxonomy priority score")
    pillar: Optional[str] = Field(default=None, description="Primary taxonomy pillar matched")


class ArticleSelectionResponse(BaseModel):
    """Schema container for structured output from Selector agent."""

    selected_articles: List[SelectedArticle] = Field(
        default_factory=list,
        description="List of top strategically relevant articles"
    )

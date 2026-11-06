"""Unit tests for HTML body text and metadata date extractor."""

import pytest

from src.scrapers.text_extractor import extract_article_from_html


def test_extract_article_from_html_body():
    """Verify cleaning scripts, styles, boilerplate, and collecting paragraphs."""
    sample_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Articol Politic</title>
        <meta property="article:published_time" content="2026-06-18T10:00:00+03:00">
        <script>console.log("tracker");</script>
        <style>.ads { color: red; }</style>
    </head>
    <body>
        <nav><a href="/">Home</a></nav>
        <h1>Titlu principal</h1>
        <p>Acesta este primul paragraf complet informativ despre negocierile din coaliție.</p>
        <p>Al doilea paragraf aduce detalii suplimentare despre poziția liderilor partidelor.</p>
        <p>cookie disclaimer text</p>
        <footer>Toate drepturile rezervate 2026</footer>
    </body>
    </html>
    """

    body, pub_date = extract_article_from_html(sample_html)
    assert "primul paragraf complet informativ" in body
    assert "detalii suplimentare despre poziția" in body
    assert "console.log" not in body
    assert "Toate drepturile rezervate" not in body
    assert pub_date == "2026-06-18"


def test_extract_metadata_time_tag():
    """Verify published date from time tag with datetime attribute."""
    sample_html = """
    <html>
    <body>
        <time datetime="2026-07-03 14:00:00">3 iulie 2026</time>
        <p>Paragraf cu conținut de test suficient de lung pentru a trece filtrul.</p>
    </body>
    </html>
    """
    body, pub_date = extract_article_from_html(sample_html)
    assert pub_date == "2026-07-03"
    assert "Paragraf cu conținut de test" in body

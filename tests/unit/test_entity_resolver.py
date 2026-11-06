"""Unit tests for Romanian entity and actor resolution."""

import pytest

from src.classification.entity_resolver import EntityResolver, normalize_string


def test_normalize_string():
    """Verify diacritics stripping and lowercase normalization."""
    assert normalize_string("Nicolae Ciucă") == "nicolae ciuca"
    assert normalize_string("Elena Lăsconi") == "elena lasconi"
    assert normalize_string("Șoșoacă Diana") == "sosoaca diana"
    assert normalize_string("   Marcel    Ciolacu   ") == "marcel ciolacu"
    assert normalize_string("") == ""


def test_resolve_key_political_leaders():
    """Verify resolution of key Romanian political figures across varied aliases."""
    cases = [
        ("Ciolacu", "Marcel Ciolacu", "PSD"),
        ("premierul Marcel Ciolacu", "Marcel Ciolacu", "PSD"),
        ("liderul psd", "Marcel Ciolacu", "PSD"),
        ("Ciucă", "Nicolae Ciucă", "PNL"),
        ("generalul Ciuca", "Nicolae Ciucă", "PNL"),
        ("Ilie Bolojan", "Ilie Bolojan", "PNL"),
        ("Iohannis", "Klaus Iohannis", "Independent"),
        ("Cotroceni", "Klaus Iohannis", "Independent"),
        ("George Simion", "George Simion", "AUR"),
        ("liderul aur", "George Simion", "AUR"),
        ("Elena Lasconi", "Elena Lasconi", "USR"),
        ("lidera usr", "Elena Lasconi", "USR"),
        ("Catalin Drula", "Cătălin Drulă", "USR"),
        ("Grindeanu", "Sorin Grindeanu", "PSD"),
        ("Alexandru Rafila", "Alexandru Rafila", "PSD"),
        ("Raluca Turcan", "Raluca Turcan", "PNL"),
        ("Kelemen Hunor", "Kelemen Hunor", "UDMR"),
        ("Diana Sosoaca", "Diana Șoșoacă", "S.O.S. România"),
        ("Mircea Geoana", "Mircea Geoană", "Independent"),
        ("Laura Codruta Kovesi", "Laura Codruța Kövesi", "Independent"),
    ]

    for raw_input, expected_canonical, expected_party in cases:
        entity = EntityResolver.resolve_actor(raw_input)
        assert entity.canonical_name == expected_canonical, f"Failed canonical for {raw_input}"
        assert entity.party == expected_party, f"Failed party for {raw_input}"


def test_resolve_political_parties():
    """Verify resolution of political parties."""
    parties = [
        ("PSD", "PSD (Partidul Social Democrat)", "PARTY"),
        ("social-democrații", "PSD (Partidul Social Democrat)", "PARTY"),
        ("PNL", "PNL (Partidul Național Liberal)", "PARTY"),
        ("USR", "USR (Uniunea Salvați România)", "PARTY"),
        ("AUR", "AUR (Alianța pentru Unirea Românilor)", "PARTY"),
        ("UDMR", "UDMR (Uniunea Democrată Maghiară din România)", "PARTY"),
    ]
    for raw_party, expected_name, expected_type in parties:
        entity = EntityResolver.resolve_actor(raw_party)
        assert entity.canonical_name == expected_name
        assert entity.entity_type == expected_type


def test_resolve_key_institutions():
    """Verify resolution of national institutions."""
    institutions = [
        ("DNA", "DNA (Direcția Națională Anticorupție)", "INSTITUTION"),
        ("procurorii dna", "DNA (Direcția Națională Anticorupție)", "INSTITUTION"),
        ("CCR", "CCR (Curtea Constituțională a României)", "INSTITUTION"),
        ("CSM", "CSM (Consiliul Superior al Magistraturii)", "INSTITUTION"),
        ("Guvernul", "Guvernul României", "INSTITUTION"),
    ]
    for raw_inst, expected_name, expected_type in institutions:
        entity = EntityResolver.resolve_actor(raw_inst)
        assert entity.canonical_name == expected_name
        assert entity.entity_type == expected_type


def test_resolve_unknown_actor():
    """Verify fallback behavior for uncatalogued actors."""
    unknown = EntityResolver.resolve_actor("Ion Popescu Necunoscut")
    assert unknown.canonical_name == "Ion Popescu Necunoscut"
    assert unknown.entity_type == "PERSON"

    empty = EntityResolver.resolve_actor("")
    assert empty.canonical_name == "Unknown Actor"
    assert empty.entity_type == "OTHER"

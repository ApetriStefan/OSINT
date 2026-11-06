"""Canonical Romanian political and institutional entity resolution module."""

import unicodedata
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


def normalize_string(text: str) -> str:
    """Normalize string, stripping accents and lowercasing."""
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return " ".join(stripped.lower().split())


class CanonicalEntity(BaseModel):
    """Resolved canonical entity metadata."""

    canonical_name: str = Field(..., description="Standardized Romanian name of the actor or entity")
    entity_type: str = Field(..., description="PERSON, PARTY, INSTITUTION, or OTHER")
    party: Optional[str] = Field(default=None, description="Political party affiliation if applicable")
    role: Optional[str] = Field(default=None, description="Current primary political or institutional role")


class EntityResolver:
    """Resolves noisy extracted Romanian political entities to canonical forms."""

    # Canonical Registry of Key Romanian Actors
    ACTORS_REGISTRY: List[Dict[str, any]] = [
        {
            "canonical_name": "Marcel Ciolacu",
            "entity_type": "PERSON",
            "party": "PSD",
            "role": "Premier al României / Președinte PSD",
            "aliases": ["ciolacu", "marcel ciolacu", "premierul ciolacu", "prim-ministrul ciolacu", "liderul psd"]
        },
        {
            "canonical_name": "Nicolae Ciucă",
            "entity_type": "PERSON",
            "party": "PNL",
            "role": "Președintele Senatului / Președinte PNL",
            "aliases": ["ciuca", "nicolae ciuca", "generalul ciuca", "liderul pnl", "presedintele pnl"]
        },
        {
            "canonical_name": "Ilie Bolojan",
            "entity_type": "PERSON",
            "party": "PNL",
            "role": "Președinte CJ Bihor / Lider PNL",
            "aliases": ["bolojan", "ilie bolojan"]
        },
        {
            "canonical_name": "Klaus Iohannis",
            "entity_type": "PERSON",
            "party": "Independent",
            "role": "Președintele României",
            "aliases": ["iohannis", "klaus iohannis", "presedintele iohannis", "seful statului", "cotroceni"]
        },
        {
            "canonical_name": "George Simion",
            "entity_type": "PERSON",
            "party": "AUR",
            "role": "Președinte AUR / Deputat",
            "aliases": ["simion", "george simion", "liderul aur"]
        },
        {
            "canonical_name": "Elena Lasconi",
            "entity_type": "PERSON",
            "party": "USR",
            "role": "Președintă USR",
            "aliases": ["lasconi", "elena lasconi", "lidera usr", "presedinta usr"]
        },
        {
            "canonical_name": "Cătălin Drulă",
            "entity_type": "PERSON",
            "party": "USR",
            "role": "Deputat USR",
            "aliases": ["drula", "catalin drula"]
        },
        {
            "canonical_name": "Sorin Grindeanu",
            "entity_type": "PERSON",
            "party": "PSD",
            "role": "Ministrul Transporturilor / Prim-vicepreședinte PSD",
            "aliases": ["grindeanu", "sorin grindeanu", "ministrul transporturilor"]
        },
        {
            "canonical_name": "Alexandru Rafila",
            "entity_type": "PERSON",
            "party": "PSD",
            "role": "Ministrul Sănătății",
            "aliases": ["rafila", "alexandru rafila", "ministrul sanatatii"]
        },
        {
            "canonical_name": "Raluca Turcan",
            "entity_type": "PERSON",
            "party": "PNL",
            "role": "Ministrul Culturii / Deputat PNL",
            "aliases": ["turcan", "raluca turcan"]
        },
        {
            "canonical_name": "Kelemen Hunor",
            "entity_type": "PERSON",
            "party": "UDMR",
            "role": "Președinte UDMR",
            "aliases": ["kelemen", "kelemen hunor", "liderul udmr"]
        },
        {
            "canonical_name": "Diana Șoșoacă",
            "entity_type": "PERSON",
            "party": "S.O.S. România",
            "role": "Europarlamentar / Președintă S.O.S. România",
            "aliases": ["sosoaca", "diana sosoaca", "senatoarea sosoaca"]
        },
        {
            "canonical_name": "Mircea Geoană",
            "entity_type": "PERSON",
            "party": "Independent",
            "role": "Fost Secretar General Adjunct NATO",
            "aliases": ["geoana", "mircea geoana", "secretar general adjunct nato"]
        },
        {
            "canonical_name": "Eugen Tomac",
            "entity_type": "PERSON",
            "party": "PMP",
            "role": "Europarlamentar / Președinte PMP",
            "aliases": ["tomac", "eugen tomac"]
        },
        {
            "canonical_name": "Laura Codruța Kövesi",
            "entity_type": "PERSON",
            "party": "Independent",
            "role": "Procuror-șef European (EPPO)",
            "aliases": ["kovesi", "koevesi", "laura codruta kovesi", "laura codruta koevesi"]
        },
        # Political Parties
        {
            "canonical_name": "PSD (Partidul Social Democrat)",
            "entity_type": "PARTY",
            "party": "PSD",
            "role": "Partid de Guvernământ",
            "aliases": ["psd", "social-democratii", "partidul social democrat"]
        },
        {
            "canonical_name": "PNL (Partidul Național Liberal)",
            "entity_type": "PARTY",
            "party": "PNL",
            "role": "Partid de Guvernământ",
            "aliases": ["pnl", "liberalii", "partidul national liberal"]
        },
        {
            "canonical_name": "USR (Uniunea Salvați România)",
            "entity_type": "PARTY",
            "party": "USR",
            "role": "Partid de Opoziție",
            "aliases": ["usr", "uniunea salvati romania"]
        },
        {
            "canonical_name": "AUR (Alianța pentru Unirea Românilor)",
            "entity_type": "PARTY",
            "party": "AUR",
            "role": "Partid de Opoziție",
            "aliases": ["aur", "alianta pentru unirea romanilor"]
        },
        {
            "canonical_name": "UDMR (Uniunea Democrată Maghiară din România)",
            "entity_type": "PARTY",
            "party": "UDMR",
            "role": "Partid Parlamentar",
            "aliases": ["udmr", "uniunea democrata maghiara din romania"]
        },
        # Key Institutions
        {
            "canonical_name": "DNA (Direcția Națională Anticorupție)",
            "entity_type": "INSTITUTION",
            "party": None,
            "role": "Parchet Anticorupție",
            "aliases": ["dna", "directia nationala anticoruptie", "procurorii dna"]
        },
        {
            "canonical_name": "CCR (Curtea Constituțională a României)",
            "entity_type": "INSTITUTION",
            "party": None,
            "role": "Curtea Constituțională",
            "aliases": ["ccr", "curtea constitutionala"]
        },
        {
            "canonical_name": "CSM (Consiliul Superior al Magistraturii)",
            "entity_type": "INSTITUTION",
            "party": None,
            "role": "Autoritate Judiciară",
            "aliases": ["csm", "consiliul superior al magistraturii"]
        },
        {
            "canonical_name": "Guvernul României",
            "entity_type": "INSTITUTION",
            "party": None,
            "role": "Executiv Național",
            "aliases": ["guvernul", "palatul victoria", "executivul"]
        }
    ]

    @classmethod
    def resolve_actor(cls, raw_actor: str) -> CanonicalEntity:
        """Resolve a raw actor string to its canonical entity."""
        if not raw_actor or not raw_actor.strip():
            return CanonicalEntity(
                canonical_name="Unknown Actor",
                entity_type="OTHER"
            )

        norm_raw = normalize_string(raw_actor)

        # 1. Exact match on normalized aliases
        for entry in cls.ACTORS_REGISTRY:
            for alias in entry["aliases"]:
                if norm_raw == alias:
                    return CanonicalEntity(
                        canonical_name=entry["canonical_name"],
                        entity_type=entry["entity_type"],
                        party=entry["party"],
                        role=entry["role"]
                    )

        # 2. Substring containment match
        for entry in cls.ACTORS_REGISTRY:
            for alias in entry["aliases"]:
                if alias in norm_raw or norm_raw in alias:
                    return CanonicalEntity(
                        canonical_name=entry["canonical_name"],
                        entity_type=entry["entity_type"],
                        party=entry["party"],
                        role=entry["role"]
                    )

        # Fallback to sanitized raw title case
        return CanonicalEntity(
            canonical_name=raw_actor.strip(),
            entity_type="PERSON" if " " in raw_actor.strip() else "OTHER"
        )

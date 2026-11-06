"""Five-pillar weighted intelligence taxonomy and noise filtering module."""

import re
import unicodedata
from typing import Dict, List, Optional, Tuple


def strip_accents(text: str) -> str:
    """Normalize and strip diacritics for robust keyword matching."""
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn").lower()


class IntelligenceTaxonomy:
    """5-Pillar weighted strategic intelligence taxonomy model with noise filtering."""

    # 1. Domestic Politics & Governance
    PILLAR_DOMESTIC_POLITICS = "domestic_politics"
    # 2. Macroeconomy & Fiscal Policy
    PILLAR_MACROECONOMY = "macroeconomy"
    # 3. National Security & Defense
    PILLAR_NATIONAL_SECURITY = "national_security"
    # 4. Justice & Anti-Corruption
    PILLAR_JUSTICE = "justice_anticorruption"
    # 5. Critical Infrastructure & Systemic Crises
    PILLAR_INFRASTRUCTURE = "critical_infrastructure"

    PILLARS: Dict[str, Dict[str, any]] = {
        PILLAR_DOMESTIC_POLITICS: {
            "weight": 1.5,
            "keywords": [
                "ciolacu", "ciuca", "tomac", "bolojan", "psd", "pnl", "usr", "aur", "udmr",
                "guvern", "ministru", "premier", "parlament", "senat", "deputati",
                "coalitie", "alegeri", "motiune", "rotativa", "presedinte", "iohannis",
                "lasconi", "simion", "sosoaca", "politica", "remaniere", "partid", "alianta"
            ]
        },
        PILLAR_MACROECONOMY: {
            "weight": 1.4,
            "keywords": [
                "pnrr", "fonduri", "licitatie", "deficit", "inflatie", "bnr", "taxe",
                "impozite", "buget", "finante", "imprumut", "datoria publica", "energie",
                "pib", "salarii", "pensii", "reforma fiscala", "anaf"
            ]
        },
        PILLAR_NATIONAL_SECURITY: {
            "weight": 1.5,
            "keywords": [
                "nato", "drone", "rusia", "ucraina", "aparare", "mapn", "frontiera",
                "armata", "militari", "marea neagra", "securitate", "patriot", "f-16",
                "infrastructura critica militara", "atac cibernetic", "sri", "sie"
            ]
        },
        PILLAR_JUSTICE: {
            "weight": 1.3,
            "keywords": [
                "dna", "diicot", "coruptie", "ancheta", "dosar", "perchezitii",
                "magistrati", "judecatori", "procurori", "csm", "justitie", "condamnare",
                "mita", "abuz in serviciu", "ccr", "curtea constitutionala", "inalta curte"
            ]
        },
        PILLAR_INFRASTRUCTURE: {
            "weight": 1.2,
            "keywords": [
                "autostrada", "cfr", "tren", "pod", "spital", "avarie", "explozie",
                "incendiu", "epidemie", "defectiune", "tragedie", "greva", "proteste",
                "blocaj", "blackout", "sistemul sanitar", "tarom"
            ]
        }
    }

    # Noise triggers (showbiz, reality TV, sports, horoscopes, weather, minor accidents)
    NOISE_PATTERNS = [
        # Showbiz & Reality TV
        r"\bsurvivor\b", r"\binsula iubirii\b", r"\basia express\b", r"\bchefi la cutite\b",
        r"\bromanii au talent\b", r"\bvedete\b", r"\bdivort\b", r"\bhoroscop\b", r"\bzodiac\b",
        r"\bcancan\b", r"\bspynews\b", r"\bmanele\b", r"\bfashion\b", r"\bcelebritati\b",
        # Sports
        r"\bfotbal\b", r"\bliga 1\b", r"\bsuperliga\b", r"\bchampions league\b", r"\bfcsb\b",
        r"\bdinamo\b", r"\brapid\b", r"\bgoluri\b", r"\bmeci\b", r"\bantrenor\b", r"\btransfer\b",
        r"\btenis\b", r"\bwta\b", r"\batp\b", r"\bsimona halep\b",
        # Weather & Minor Accidents
        r"\bprognoza meteo\b", r"\bcod galben de\b", r"\bcod portocaliu de canicula\b",
        r"\btamponare\b", r"\baccident rutier usor\b"
    ]

    @classmethod
    def is_noise(cls, title: str, text: str = "") -> bool:
        """Determine if an article is classified as noise and should be filtered out."""
        combined_normalized = strip_accents(f"{title} {text[:500]}")
        for pattern in cls.NOISE_PATTERNS:
            if re.search(pattern, combined_normalized):
                # Ensure it's not a false positive with high strategic keywords
                if not any(k in combined_normalized for k in ["ciolacu", "premier", "nato", "dna", "pnrr"]):
                    return True
        return False

    @classmethod
    def score_article(
        cls,
        title: str,
        summary: str = "",
        text: str = ""
    ) -> Tuple[float, Optional[str], Dict[str, float]]:
        """Calculate weighted strategic intelligence score and match primary pillar.

        Returns:
            Tuple of (total_score, primary_pillar, pillar_breakdown)
        """
        if cls.is_noise(title, text):
            return 0.0, None, {}

        # Title keywords carry 3x weight compared to summary/body
        title_norm = strip_accents(title)
        body_norm = strip_accents(f"{summary} {text[:2000]}")

        pillar_scores: Dict[str, float] = {}
        total_score = 0.0
        primary_pillar: Optional[str] = None
        max_pillar_score = 0.0

        for pillar_name, pillar_info in cls.PILLARS.items():
            pillar_weight = pillar_info["weight"]
            keywords = pillar_info["keywords"]
            matches_title = sum(1 for kw in keywords if re.search(rf"\b{kw}\b", title_norm))
            matches_body = sum(1 for kw in keywords if re.search(rf"\b{kw}\b", body_norm))

            score = (matches_title * 3.0 + matches_body * 1.0) * pillar_weight
            pillar_scores[pillar_name] = round(score, 2)
            total_score += score

            if score > max_pillar_score:
                max_pillar_score = score
                primary_pillar = pillar_name

        return round(total_score, 2), primary_pillar, pillar_scores

"""Unit tests for the 5-pillar strategic taxonomy model and noise filtering."""

import pytest

from src.classification.taxonomy import IntelligenceTaxonomy, strip_accents


def test_strip_accents():
    """Verify diacritics stripping for Romanian text."""
    assert strip_accents("Ședință de Coaliție și Moțiune") == "sedinta de coalitie si motiune"
    assert strip_accents("Împrumuturi și Deficit Bugetar") == "imprumuturi si deficit bugetar"


def test_noise_filtering_reality_tv_and_showbiz():
    """Verify noise filter catches showbiz and reality TV topics."""
    noisy_titles = [
        "Eliminare șoc la Survivor România: Cine a părăsit competiția",
        "Momente dramatice la Insula Iubirii: Ispita a făcut mărturisiri",
        "Horoscop zilnic: Zodiile care au noroc la bani astăzi",
        "Vedete surprinse la mare în ipostaze incendiare",
        "Cine a câștigat marele premiu la Românii au Talent",
    ]
    for title in noisy_titles:
        assert IntelligenceTaxonomy.is_noise(title), f"Expected noise for: {title}"


def test_noise_filtering_sports():
    """Verify noise filter catches sports events."""
    sports_titles = [
        "FCSB s-a calificat în grupele Champions League după un meci de infarct",
        "Transfer de senzație în Superligă la Dinamo",
        "Simona Halep a câștigat turneul WTA după un meci strâns",
        "Antrenorul echipei naționale de fotbal a anunțat lotul",
    ]
    for title in sports_titles:
        assert IntelligenceTaxonomy.is_noise(title), f"Expected noise for: {title}"


def test_noise_filtering_weather_and_minor():
    """Verify noise filter catches weather forecasts and minor accidents."""
    minor_titles = [
        "Prognoza meteo pentru weekend: Val de caniculă și cod galben",
        "Tamponare ușoară în centrul Capitalei între două autoturisme",
    ]
    for title in minor_titles:
        assert IntelligenceTaxonomy.is_noise(title), f"Expected noise for: {title}"


def test_strategic_news_not_filtered_as_noise():
    """Verify that legitimate political news is not dropped by noise filter."""
    strategic_titles = [
        "Marcel Ciolacu anunță măsuri dure pentru reducerea deficitului bugetar",
        "Drone rusești detectate lângă granița României: Alertă NATO la Marea Neagră",
        "DNA a descins la sediul Ministerului pentru contracte PNRR suspecte",
        "Elena Lasconi cere demisia guvernului după scandalul licitațiilor",
        "Scandal în Senat: Moțiune simplă împotriva ministrului Energiei",
    ]
    for title in strategic_titles:
        assert not IntelligenceTaxonomy.is_noise(title), f"False positive noise for: {title}"


def test_taxonomy_pillar_scoring():
    """Verify that articles score in the appropriate strategic pillar."""
    # Domestic politics
    pol_title = "Marcel Ciolacu și Nicolae Ciucă convoacă ședința de coaliție pentru alegeri"
    score, pillar, breakdown = IntelligenceTaxonomy.score_article(pol_title)
    assert score > 0
    assert pillar == IntelligenceTaxonomy.PILLAR_DOMESTIC_POLITICS
    assert breakdown[IntelligenceTaxonomy.PILLAR_DOMESTIC_POLITICS] > 0

    # Macroeconomy
    econ_title = "Deficitul bugetar și fondurile PNRR: Avertismentul BNR privind noile taxe"
    score, pillar, breakdown = IntelligenceTaxonomy.score_article(econ_title)
    assert score > 0
    assert pillar == IntelligenceTaxonomy.PILLAR_MACROECONOMY
    assert breakdown[IntelligenceTaxonomy.PILLAR_MACROECONOMY] > 0

    # National security
    sec_title = "Exercițiu militar NATO în Marea Neagră: MApN trimite avioane F-16"
    score, pillar, breakdown = IntelligenceTaxonomy.score_article(sec_title)
    assert score > 0
    assert pillar == IntelligenceTaxonomy.PILLAR_NATIONAL_SECURITY
    assert breakdown[IntelligenceTaxonomy.PILLAR_NATIONAL_SECURITY] > 0

    # Justice
    just_title = "Procurorii DNA au trimis în judecată fostul director pentru mită și abuz în serviciu"
    score, pillar, breakdown = IntelligenceTaxonomy.score_article(just_title)
    assert score > 0
    assert pillar == IntelligenceTaxonomy.PILLAR_JUSTICE
    assert breakdown[IntelligenceTaxonomy.PILLAR_JUSTICE] > 0

    # Infrastructure
    infra_title = "Accident grav pe calea ferată CFR: Circulație feroviară blocată pe magistrală"
    score, pillar, breakdown = IntelligenceTaxonomy.score_article(infra_title)
    assert score > 0
    assert pillar == IntelligenceTaxonomy.PILLAR_INFRASTRUCTURE
    assert breakdown[IntelligenceTaxonomy.PILLAR_INFRASTRUCTURE] > 0

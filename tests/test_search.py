"""
Teste automate pentru logica de combinare/filtrare. NU fac cereri pe internet,
deci rulează instant și dau mereu același rezultat.

Rulare (din folderul proiectului, cu venv activat):   pytest
Fiecare funcție care începe cu "test_" e un test; "assert" verifică o condiție.
Dacă modifici ceva în app/search.py sau app/sources/ și un test pică, ai stricat ceva ce mergea.
"""

from app.models import Article
from app.search import apply_filters, is_emg_related, merge_articles
from app.sources import openalex, semantic_scholar


def art(title, **kw) -> Article:
    return Article(title=title, **kw)


def test_rebuild_abstract_from_inverted_index():
    inverted = {"Surface": [0], "EMG": [1, 3], "is": [2]}
    assert openalex.rebuild_abstract(inverted) == "Surface EMG is EMG"
    assert openalex.rebuild_abstract(None) is None


def test_openalex_query_adds_emg_terms_and_strips_special_chars():
    q = openalex.build_query("hand, muscle | fatigue")
    assert q.startswith("(hand muscle fatigue) AND (")
    assert "electromyography" in q and "," not in q and "|" not in q


def test_semantic_scholar_query_adds_term_only_when_missing():
    assert semantic_scholar.build_query("hand muscle") == "hand muscle electromyography"
    assert semantic_scholar.build_query("hand sEMG") == "hand sEMG"


def test_emg_filter():
    assert is_emg_related(art("Surface electromyography of the forearm"))
    assert is_emg_related(art("HD-EMG decomposition"))
    assert is_emg_related(art("Something", abstract="We used myoelectric control."))
    assert not is_emg_related(art("Hand anatomy in primates"))
    assert not is_emg_related(art("Emgality drug trial"))  # "emg" în interiorul unui cuvânt nu contează


def test_merge_removes_duplicates_by_doi_and_fills_missing_fields():
    a1 = art("EMG control", doi="10.1/ABC", sources=["OpenAlex"], citation_count=5)
    a2 = art("EMG Control.", doi="10.1/abc", abstract="text", sources=["Semantic Scholar"], citation_count=9)
    merged = merge_articles([[a1], [a2]])
    assert len(merged) == 1
    assert merged[0].abstract == "text"
    assert merged[0].citation_count == 9
    assert merged[0].sources == ["OpenAlex", "Semantic Scholar"]


def test_merge_matches_by_title_when_one_has_no_doi():
    merged = merge_articles([[art("EMG-based Control", doi="10.1/x")], [art("emg based control")]])
    assert len(merged) == 1


def test_merge_interleaves_sources():
    merged = merge_articles([[art("A1"), art("A2")], [art("B1"), art("B2")]])
    assert [a.title for a in merged] == ["A1", "B1", "A2", "B2"]


def test_filters_and_sorting():
    items = [
        art("old", year=2001, citation_count=100),
        art("new", year=2023, citation_count=3, is_open_access=True),
        art("noyear"),
    ]
    assert [a.title for a in apply_filters(items, year_from=2010)] == ["new"]
    assert [a.title for a in apply_filters(items, open_access_only=True)] == ["new"]
    assert [a.title for a in apply_filters(items, sort="citations")][0] == "old"
    assert [a.title for a in apply_filters(items, sort="year")][0] == "new"

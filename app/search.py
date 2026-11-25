"""
"Creierul" aplicației: combină sursele într-un singur rezultat.

Pașii unei căutări:
  1. verifică dacă avem deja rezultatul în cache (memorie), ca să nu întrebăm din nou API-urile;
  2. întreabă TOATE sursele în paralel (nu una după alta), deci timpul total ≈ cea mai lentă sursă;
  3. combină articolele: elimină dublurile (același articol găsit în 2 surse);
  4. păstrează doar articolele care sunt despre EMG (filtrul de domeniu);
  5. aplică filtrele alese de utilizator (ani, open access) și ordonarea.

Funcțiile mici (normalize_title, is_emg_related, merge_articles...) nu fac cereri pe internet,
deci pot fi testate ușor (vezi tests/test_search.py).
"""

import asyncio
import re
import time
from dataclasses import dataclass, field

import httpx

from app import config
from app.models import Article, Dataset, SourceResult
from app.sources import huggingface, openalex, semantic_scholar

# Sursele de articole și de seturi de date. Ca să adaugi o sursă, o pui în lista potrivită.
ARTICLE_SOURCES = [openalex, semantic_scholar]
DATASET_SOURCES = [huggingface]

_EMG_REGEXES = [re.compile(p, re.IGNORECASE) for p in config.EMG_FILTER_PATTERNS]


@dataclass
class SearchResults:
    """Tot ce primește pagina HTML după o căutare."""

    query: str
    articles: list[Article] = field(default_factory=list)
    datasets: list[Dataset] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)          # sursă -> mesaj de eroare
    counts: dict[str, int] = field(default_factory=dict)          # sursă -> câte rezultate a dat
    filtered_out: int = 0                                         # câte articole am aruncat (nu erau despre EMG)
    duration_s: float = 0.0
    from_cache: bool = False


# ---------------------------------------------------------------------------
# Funcții ajutătoare (fără internet, ușor de testat)
# ---------------------------------------------------------------------------

def normalize_title(title: str) -> str:
    """Titlu redus la litere mici și cifre, ca "EMG-Based Control." și "emg based control" să fie egale."""
    return re.sub(r"[^a-z0-9]", "", title.lower())


def article_key(article: Article) -> str:
    """Cheia după care recunoaștem același articol din surse diferite: DOI-ul, sau titlul dacă nu are DOI."""
    if article.doi:
        return "doi:" + article.doi.lower().strip()
    return "title:" + normalize_title(article.title)


def is_emg_related(article: Article) -> bool:
    """True dacă titlul sau rezumatul conține cel puțin un termen EMG (din config.EMG_FILTER_PATTERNS)."""
    text = f"{article.title} {article.abstract or ''}"
    return any(rx.search(text) for rx in _EMG_REGEXES)


def merge_articles(result_lists: list[list[Article]]) -> list[Article]:
    """Combină listele de la surse, eliminând dublurile.

    Când același articol vine din 2 surse, păstrăm prima variantă (OpenAlex e prima în listă)
    și completăm câmpurile lipsă din a doua (ex: rezumatul, linkul spre PDF).
    Ordinea finală: alternăm sursele (1 de la OpenAlex, 1 de la Semantic Scholar, ...),
    ca cele mai relevante rezultate ale fiecărei surse să apară sus.
    """
    merged: dict[str, Article] = {}  # dicționarele Python păstrează ordinea inserării
    by_title: dict[str, str] = {}    # titlu normalizat -> cheie, ca să prindem și dublurile unde doar una are DOI

    longest = max((len(lst) for lst in result_lists), default=0)
    for i in range(longest):
        for lst in result_lists:
            if i >= len(lst):
                continue
            art = lst[i]
            key = article_key(art)
            title_key = normalize_title(art.title)
            existing_key = key if key in merged else by_title.get(title_key)

            if existing_key is None:
                merged[key] = art.model_copy(deep=True)
                by_title.setdefault(title_key, key)
                continue

            # Dublură: completăm ce lipsește în varianta pe care o avem deja.
            kept = merged[existing_key]
            for field_name in ("abstract", "doi", "pdf_url", "venue", "year", "citation_count"):
                if getattr(kept, field_name) in (None, "") and getattr(art, field_name) not in (None, ""):
                    setattr(kept, field_name, getattr(art, field_name))
            if not kept.authors and art.authors:
                kept.authors = art.authors
            kept.is_open_access = kept.is_open_access or art.is_open_access
            # Numărul de citări diferă între surse; păstrăm valoarea mai mare.
            if art.citation_count is not None and (kept.citation_count or 0) < art.citation_count:
                kept.citation_count = art.citation_count
            for s in art.sources:
                if s not in kept.sources:
                    kept.sources.append(s)

    return list(merged.values())


def apply_filters(
    articles: list[Article],
    year_from: int | None = None,
    year_to: int | None = None,
    open_access_only: bool = False,
    sort: str = "relevance",
) -> list[Article]:
    """Filtrele și ordonarea alese de utilizator în pagină."""
    result = [
        a for a in articles
        if (year_from is None or (a.year is not None and a.year >= year_from))
        and (year_to is None or (a.year is not None and a.year <= year_to))
        and (not open_access_only or a.is_open_access)
    ]
    if sort == "year":
        result.sort(key=lambda a: a.year or 0, reverse=True)
    elif sort == "citations":
        result.sort(key=lambda a: a.citation_count or 0, reverse=True)
    # "relevance" = ordinea dată de surse (deja cea bună)
    return result


# ---------------------------------------------------------------------------
# Cache simplu în memorie: căutare -> (momentul salvării, rezultate)
# Se pierde la repornirea serverului. Mai târziu poate fi mutat în SQLite.
# ---------------------------------------------------------------------------
_cache: dict[str, tuple[float, SearchResults]] = {}


def _cache_get(query: str) -> SearchResults | None:
    entry = _cache.get(query.lower())
    if entry and time.time() - entry[0] < config.CACHE_TTL_SECONDS:
        return entry[1]
    return None


def _cache_put(query: str, results: SearchResults) -> None:
    # Nu salvăm rezultatele dacă o sursă a dat eroare: data viitoare poate merge.
    if not results.errors:
        _cache[query.lower()] = (time.time(), results)


# ---------------------------------------------------------------------------
# Funcția principală
# ---------------------------------------------------------------------------

async def search_all(query: str) -> SearchResults:
    """Caută în toate sursele și returnează rezultatele combinate (nefiltrate de utilizator)."""
    query = query.strip()
    cached = _cache_get(query)
    if cached:
        return SearchResults(**{**cached.__dict__, "from_cache": True})

    start = time.perf_counter()
    # Un singur "client" HTTP refolosit pentru toate cererile (mai eficient decât câte unul pe cerere).
    # User-Agent-ul identifică aplicația față de servere; e o practică bună de politețe.
    async with httpx.AsyncClient(
        timeout=config.HTTP_TIMEOUT_SECONDS,
        headers={"User-Agent": "emg-search/0.1 (academic project)"},
    ) as client:
        all_sources = ARTICLE_SOURCES + DATASET_SOURCES
        # asyncio.gather pornește toate căutările deodată și așteaptă să se termine toate.
        source_results: list[SourceResult] = await asyncio.gather(
            *(src.search(client, query) for src in all_sources)
        )

    results = SearchResults(query=query)
    article_lists: list[list[Article]] = []
    for sr in source_results:
        if sr.error:
            results.errors[sr.source] = sr.error
        results.counts[sr.source] = len(sr.articles) + len(sr.datasets)
        if sr.articles:
            article_lists.append(sr.articles)
        results.datasets.extend(sr.datasets)

    merged = merge_articles(article_lists)
    # Articolele de la OpenAlex au trecut deja printr-un filtru EMG pe titlu+rezumat la ei pe server
    # (vezi openalex.build_query), chiar dacă uneori nu ne trimit rezumatul. Le păstrăm.
    # Pe celelalte le verificăm noi.
    results.articles = [a for a in merged if openalex.SOURCE_NAME in a.sources or is_emg_related(a)]
    results.filtered_out = len(merged) - len(results.articles)
    results.duration_s = round(time.perf_counter() - start, 2)

    _cache_put(query, results)
    return results

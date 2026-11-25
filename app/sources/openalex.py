"""
Sursa OpenAlex: catalog deschis cu sute de milioane de publicații științifice.
Documentație: https://docs.openalex.org

Cum arată cererea pe care o trimitem (o poți lipi și în browser ca să vezi JSON-ul):
  https://api.openalex.org/works?filter=title_and_abstract.search:(hand muscle) AND (electromyography OR EMG)&per_page=25

- "works" = colecția de publicații
- filter=title_and_abstract.search:... = caută DOAR în titlu și rezumat. Am ales asta în loc de
  parametrul "search", care caută și în textul complet și dă rezultate mult mai puțin relevante.
- AND / OR (cu litere mari) = operatori logici înțeleși de OpenAlex
- select=... = cerem doar câmpurile de care avem nevoie (răspuns mai mic, mai rapid)
"""

import re

import httpx

from app import config
from app.models import Article, SourceResult

SOURCE_NAME = "OpenAlex"
BASE_URL = "https://api.openalex.org/works"

FIELDS = [
    "id", "doi", "title", "publication_year", "authorships", "primary_location",
    "open_access", "best_oa_location", "cited_by_count", "abstract_inverted_index",
]


def build_query(user_query: str) -> str:
    """Construiește textul de căutare: (ce a scris utilizatorul) AND (termenii EMG).

    Eliminăm caracterele care au rol special în sintaxa filtrelor OpenAlex
    (virgula separă filtre, | înseamnă "sau", : separă numele de valoare),
    altfel o căutare cu virgulă ar strica cererea.
    """
    cleaned = re.sub(r"[,|:()]", " ", user_query)
    cleaned = " ".join(cleaned.split())  # comprimă spațiile multiple
    emg_part = " OR ".join(config.EMG_QUERY_TERMS)
    return f"({cleaned}) AND ({emg_part})"


def rebuild_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """OpenAlex nu dă rezumatul ca text, ci ca "index inversat" (din motive de drepturi de autor):
        {"Surface": [0], "electromyography": [1, 7], ...}  = cuvânt -> pozițiile la care apare
    Îl refacem: punem fiecare cuvânt pe poziția lui, apoi le lipim cu spații.
    """
    if not inverted_index:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


def parse_work(work: dict) -> Article:
    """Traduce un rezultat OpenAlex (dicționar JSON) în clasa noastră Article."""
    primary = work.get("primary_location") or {}
    venue = (primary.get("source") or {}).get("display_name")
    open_access = work.get("open_access") or {}
    best_oa = work.get("best_oa_location") or {}

    doi = work.get("doi")  # vine ca "https://doi.org/10.xxx"; păstrăm doar partea "10.xxx"
    if doi:
        doi = doi.replace("https://doi.org/", "")

    return Article(
        title=work.get("title") or "(fără titlu)",
        authors=[
            a["author"]["display_name"]
            for a in work.get("authorships") or []
            if a.get("author") and a["author"].get("display_name")
        ],
        year=work.get("publication_year"),
        venue=venue,
        abstract=rebuild_abstract(work.get("abstract_inverted_index")),
        doi=doi,
        url=f"https://doi.org/{doi}" if doi else (primary.get("landing_page_url") or work.get("id")),
        pdf_url=best_oa.get("pdf_url") or open_access.get("oa_url"),
        is_open_access=bool(open_access.get("is_oa")),
        citation_count=work.get("cited_by_count"),
        sources=[SOURCE_NAME],
    )


async def search(client: httpx.AsyncClient, user_query: str) -> SourceResult:
    """Trimite căutarea la OpenAlex și returnează articolele găsite."""
    params = {
        "filter": f"title_and_abstract.search:{build_query(user_query)}",
        "per_page": config.RESULTS_PER_SOURCE,
        "select": ",".join(FIELDS),
    }
    if config.OPENALEX_API_KEY:
        params["api_key"] = config.OPENALEX_API_KEY

    try:
        response = await client.get(BASE_URL, params=params)
        response.raise_for_status()  # aruncă excepție dacă statusul HTTP e de eroare (4xx/5xx)
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 429:
            msg = "limita de cereri a fost atinsă (adaugă OPENALEX_API_KEY în .env)"
        elif status in (401, 403):
            msg = "cheia API OpenAlex nu e validă (verifică OPENALEX_API_KEY din .env)"
        else:
            msg = f"eroare HTTP {status}"
        return SourceResult(source=SOURCE_NAME, error=msg)
    except httpx.HTTPError as e:  # fără internet, timeout, etc.
        return SourceResult(source=SOURCE_NAME, error=f"nu s-a putut contacta serverul ({type(e).__name__})")

    works = response.json().get("results", [])
    return SourceResult(source=SOURCE_NAME, articles=[parse_work(w) for w in works])

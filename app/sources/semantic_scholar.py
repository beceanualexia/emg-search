"""
Sursa Semantic Scholar (Allen Institute for AI): alt catalog mare de publicații.
Documentație: https://api.semanticscholar.org/api-docs/graph

Exemplu de cerere:
  https://api.semanticscholar.org/graph/v1/paper/search?query=hand muscle electromyography&limit=25&fields=title,year,...

Spre deosebire de OpenAlex, căutarea de aici NU înțelege AND/OR, așa că doar adăugăm
"electromyography" la text, dacă utilizatorul n-a scris deja un termen EMG.
Restul filtrării pe EMG o face app/search.py după ce primim rezultatele.

ATENȚIE: fără cheie API, Semantic Scholar refuză des cererile (cod 429 = "Too Many Requests"),
pentru că toți utilizatorii fără cheie împart aceeași cotă. Cheia e gratuită (vezi .env.example).
"""

import asyncio
import re

import httpx

from app import config
from app.models import Article, SourceResult

SOURCE_NAME = "Semantic Scholar"
BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,year,authors,venue,abstract,externalIds,url,openAccessPdf,isOpenAccess,citationCount"


def build_query(user_query: str) -> str:
    """Adaugă "electromyography" doar dacă textul nu conține deja un termen EMG."""
    has_emg_term = any(re.search(p, user_query, re.IGNORECASE) for p in config.EMG_FILTER_PATTERNS)
    return user_query if has_emg_term else f"{user_query} electromyography"


def parse_paper(paper: dict) -> Article:
    """Traduce un rezultat Semantic Scholar în clasa noastră Article."""
    doi = (paper.get("externalIds") or {}).get("DOI")
    pdf = (paper.get("openAccessPdf") or {}).get("url") or None
    return Article(
        title=paper.get("title") or "(fără titlu)",
        authors=[a["name"] for a in paper.get("authors") or [] if a.get("name")],
        year=paper.get("year"),
        venue=paper.get("venue") or None,
        abstract=paper.get("abstract"),
        doi=doi,
        url=f"https://doi.org/{doi}" if doi else paper.get("url"),
        pdf_url=pdf,
        is_open_access=bool(paper.get("isOpenAccess")),
        citation_count=paper.get("citationCount"),
        sources=[SOURCE_NAME],
    )


async def search(client: httpx.AsyncClient, user_query: str) -> SourceResult:
    params = {"query": build_query(user_query), "limit": config.RESULTS_PER_SOURCE, "fields": FIELDS}
    headers = {"x-api-key": config.SEMANTIC_SCHOLAR_API_KEY} if config.SEMANTIC_SCHOLAR_API_KEY else {}

    try:
        response = await client.get(BASE_URL, params=params, headers=headers)
        if response.status_code == 429:
            # Mai încercăm o dată după o pauză scurtă; de multe ori a doua oară merge.
            await asyncio.sleep(2)
            response = await client.get(BASE_URL, params=params, headers=headers)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 429:
            msg = "serverul a refuzat temporar cererea (prea multe cereri). Încearcă din nou sau adaugă SEMANTIC_SCHOLAR_API_KEY în .env"
        elif status in (401, 403):
            msg = "cheia API Semantic Scholar nu e validă (verifică .env)"
        else:
            msg = f"eroare HTTP {status}"
        return SourceResult(source=SOURCE_NAME, error=msg)
    except httpx.HTTPError as e:
        return SourceResult(source=SOURCE_NAME, error=f"nu s-a putut contacta serverul ({type(e).__name__})")

    papers = response.json().get("data") or []
    return SourceResult(source=SOURCE_NAME, articles=[parse_paper(p) for p in papers])

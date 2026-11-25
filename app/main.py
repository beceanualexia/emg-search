"""
Punctul de intrare al aplicației web (serverul).

Cum funcționează un site, pe scurt:
  - browserul cere o adresă (ex: http://127.0.0.1:8000/?q=hand+muscle);
  - FastAPI găsește funcția asociată acelei adrese (o "rută", marcată cu @app.get(...));
  - funcția primește parametrii din adresă (q=hand muscle), face căutarea,
    completează un șablon HTML cu rezultatele și îl trimite înapoi browserului.

Rute:
  /             -> pagina de căutare (HTML, pentru oameni)
  /api/search   -> aceleași rezultate în JSON (pentru programe/scripturi, ex: din Python sau Excel)
  /docs         -> documentație interactivă generată automat de FastAPI (poți testa /api/search de acolo)

Pornire (din folderul proiectului, cu venv activat):
  uvicorn app.main:app --reload
"""

from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import config
from app.search import apply_filters, search_all

BASE_DIR = Path(__file__).parent

app = FastAPI(
    title="EMG Literature Search",
    description="Caută articole și seturi de date despre electromiografie (EMG) în mai multe surse.",
    version="0.1.0",
)

# Fișierele statice (CSS) sunt servite la adresa /static/...
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _parse_year(value: str | None) -> int | None:
    """Transformă textul din formular într-un an (sau None dacă e gol/invalid)."""
    if value and value.strip().isdigit():
        return int(value.strip())
    return None


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    q: str = "",
    year_from: str | None = None,
    year_to: str | None = None,
    oa: bool = False,
    sort: str = "relevance",
    tab: str = "articles",
):
    """Pagina principală. Fără "q" arată doar formularul; cu "q" arată și rezultatele.

    Parametrii vin din adresa URL (formularul HTML folosește metoda GET),
    deci orice căutare poate fi salvată/trimisă ca link.
    """
    context = {
        "q": q, "year_from": year_from or "", "year_to": year_to or "", "oa": oa,
        "sort": sort, "tab": tab, "results": None, "articles": [],
        "has_keys": {
            "OpenAlex": bool(config.OPENALEX_API_KEY),
            "Semantic Scholar": bool(config.SEMANTIC_SCHOLAR_API_KEY),
        },
    }
    if q.strip():
        results = await search_all(q)
        context["results"] = results
        context["articles"] = apply_filters(
            results.articles, _parse_year(year_from), _parse_year(year_to), oa, sort
        )
    return templates.TemplateResponse(request, "index.html", context)


@app.get("/api/search")
async def api_search(
    q: str = Query(..., min_length=2, description="Textul căutat, ex: hand muscle"),
    year_from: int | None = None,
    year_to: int | None = None,
    oa: bool = False,
    sort: str = Query("relevance", pattern="^(relevance|year|citations)$"),
):
    """Aceeași căutare, dar răspunsul e JSON (date brute, fără HTML)."""
    results = await search_all(q)
    articles = apply_filters(results.articles, year_from, year_to, oa, sort)
    return {
        "query": results.query,
        "counts": results.counts,
        "errors": results.errors,
        "filtered_out_non_emg": results.filtered_out,
        "articles": [a.model_dump() for a in articles],
        "datasets": [d.model_dump() for d in results.datasets],
    }

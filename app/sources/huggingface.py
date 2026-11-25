"""
Sursa Hugging Face: platformă pentru seturi de date și modele de machine learning.
Aici NU căutăm articole, ci SETURI DE DATE EMG (înregistrări de semnal pe care le poți descărca).
Documentație: https://huggingface.co/docs/hub/api

Problema: căutarea Hugging Face e foarte simplă. Caută doar textul exact în numele setului
de date, deci "hand muscle emg" nu găsește nimic. Soluția noastră:
  1. aducem TOATE seturile de date care au în nume un termen EMG (emg, electromyography, myo...);
  2. le ordonăm noi după câte cuvinte din căutarea utilizatorului apar în nume/descriere/etichete.

Exemplu de cerere:  https://huggingface.co/api/datasets?search=emg&limit=100
"""

import asyncio
import re

import httpx

from app import config
from app.models import Dataset, SourceResult

SOURCE_NAME = "Hugging Face"
BASE_URL = "https://huggingface.co/api/datasets"

# Termenii cu care întrebăm Hugging Face. Sunt subșiruri din numele seturilor de date.
HF_SEARCH_TERMS = ["emg", "electromyograph", "myoelectric", "ninapro"]

# Cuvinte prea generale ca să conteze la ordonare.
STOPWORDS = {"the", "a", "an", "of", "and", "or", "for", "in", "on", "with", "to", "emg", "semg"}


def parse_dataset(item: dict) -> Dataset:
    """Traduce un rezultat Hugging Face în clasa noastră Dataset."""
    dataset_id = item["id"]
    description = (item.get("description") or "").strip()
    description = " ".join(description.split())  # curăță spațiile/tab-urile din descriere
    # Etichetele de tip "region:us" sau "library:pandas" nu ajută utilizatorul; le păstrăm pe celelalte.
    tags = [t for t in item.get("tags") or [] if not t.startswith(("region:", "library:"))]
    return Dataset(
        id=dataset_id,
        title=dataset_id.split("/")[-1],
        description=description or None,
        url=f"https://huggingface.co/datasets/{dataset_id}",
        downloads=item.get("downloads") or 0,
        likes=item.get("likes") or 0,
        last_modified=(item.get("lastModified") or "")[:10] or None,  # păstrăm doar data, ex: 2024-03-25
        tags=tags,
    )


def relevance_score(dataset: Dataset, user_query: str) -> int:
    """Câte cuvinte din căutare apar în numele, descrierea sau etichetele setului de date."""
    words = {w for w in re.findall(r"[a-z0-9]+", user_query.lower()) if w not in STOPWORDS and len(w) > 2}
    haystack = " ".join([dataset.id, dataset.description or "", " ".join(dataset.tags)]).lower()
    return sum(1 for w in words if w in haystack)


async def _fetch_term(client: httpx.AsyncClient, term: str) -> list[dict]:
    response = await client.get(BASE_URL, params={"search": term, "limit": config.HF_DATASETS_LIMIT, "full": "false"})
    response.raise_for_status()
    return response.json()


async def search(client: httpx.AsyncClient, user_query: str) -> SourceResult:
    try:
        # Trimitem câte o cerere pentru fiecare termen, toate în paralel (asyncio.gather).
        batches = await asyncio.gather(*(_fetch_term(client, t) for t in HF_SEARCH_TERMS))
    except httpx.HTTPStatusError as e:
        return SourceResult(source=SOURCE_NAME, error=f"eroare HTTP {e.response.status_code}")
    except httpx.HTTPError as e:
        return SourceResult(source=SOURCE_NAME, error=f"nu s-a putut contacta serverul ({type(e).__name__})")

    # Același set de date poate apărea la mai mulți termeni; un dicționar după id elimină dublurile.
    unique: dict[str, Dataset] = {}
    for batch in batches:
        for item in batch:
            if item.get("private") or item.get("disabled"):
                continue
            unique.setdefault(item["id"], parse_dataset(item))

    # Ordonăm: întâi cele mai relevante pentru căutare, apoi cele mai descărcate.
    datasets = sorted(
        unique.values(),
        key=lambda d: (relevance_score(d, user_query), d.downloads, d.likes),
        reverse=True,
    )
    return SourceResult(source=SOURCE_NAME, datasets=datasets)

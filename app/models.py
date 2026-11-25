"""
Modelele de date: "formatul comun" în care aducem rezultatele de la toate sursele.

Fiecare platformă returnează JSON cu altă structură (OpenAlex zice "publication_year",
Semantic Scholar zice "year", etc.). Fiecare fișier din app/sources/ traduce JSON-ul
platformei în aceste clase. Restul aplicației lucrează DOAR cu aceste clase, deci
nu trebuie să știe nimic despre formatul fiecărei platforme.

Folosim Pydantic (BaseModel): e ca o clasă normală din OOP, dar verifică automat
tipurile câmpurilor (ex: year chiar e int sau None).
"""

from pydantic import BaseModel, Field


class Article(BaseModel):
    """O publicație științifică (articol, lucrare de conferință, teză...)."""

    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None            # revista sau conferința
    abstract: str | None = None
    doi: str | None = None              # identificator unic al articolului, ex: 10.1109/xyz
    url: str | None = None              # unde poate fi citit articolul
    pdf_url: str | None = None          # link direct spre PDF, dacă e open access
    is_open_access: bool = False
    citation_count: int | None = None
    sources: list[str] = Field(default_factory=list)  # de unde a venit: ["OpenAlex", "Semantic Scholar"]


class Dataset(BaseModel):
    """Un set de date (ex: înregistrări EMG) sau alt material de pe Hugging Face."""

    id: str                             # ex: "autor/nume-set-date"
    title: str
    description: str | None = None
    url: str
    downloads: int = 0
    likes: int = 0
    last_modified: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: str = "Hugging Face"


class SourceResult(BaseModel):
    """Ce returnează fiecare sursă: rezultatele + o eroare, dacă ceva n-a mers.

    Ținem eroarea separat ca o sursă căzută să nu strice toată pagina:
    afișăm ce avem de la celelalte și un mesaj despre cea care a eșuat.
    """

    source: str
    articles: list[Article] = Field(default_factory=list)
    datasets: list[Dataset] = Field(default_factory=list)
    error: str | None = None

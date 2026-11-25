"""
Configurare: totul ce ai putea vrea să ajustezi fără să umbli la logică.

- cheile API (citite din fișierul .env)
- termenii care definesc domeniul "EMG"
- câte rezultate cerem de la fiecare sursă
"""

import os

from dotenv import load_dotenv

# Citește fișierul .env (dacă există) și pune valorile în variabilele de mediu.
load_dotenv()

OPENALEX_API_KEY: str = os.getenv("OPENALEX_API_KEY", "").strip()
SEMANTIC_SCHOLAR_API_KEY: str = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()

# --- Domeniul EMG --------------------------------------------------------------
# Acești termeni sunt folosiți în două locuri:
#   1. se adaugă la căutare, ca sursele să caute doar în zona EMG;
#   2. se verifică în titlu/rezumat, ca să aruncăm rezultatele care nu sunt despre EMG.
# Dacă vrei să lărgești/îngustezi domeniul, aici modifici.
EMG_QUERY_TERMS: list[str] = [
    "electromyography",
    "electromyographic",
    "EMG",
    "sEMG",
    "myoelectric",
]

# Expresii regulate (regex) folosite la filtrare. \b = "graniță de cuvânt",
# ca "emg" să nu se potrivească în mijlocul altui cuvânt.
# re.IGNORECASE se aplică în search.py, deci nu contează literele mari/mici.
EMG_FILTER_PATTERNS: list[str] = [
    r"electromyogra",   # electromyography, electromyographic, electromyogram
    r"\b(?:s|i|f|hd|hd-s)?emg\b",  # EMG, sEMG, iEMG, fEMG, HDEMG, HD-EMG, HD-sEMG

    r"myoelectric",     # myoelectric control, myoelectrical
    r"\bmyo[- ]?signal",
]

# --- Limite -------------------------------------------------------------------
RESULTS_PER_SOURCE: int = 25      # câte articole cerem de la fiecare sursă de articole
HF_DATASETS_LIMIT: int = 100      # câte seturi de date EMG aducem de pe Hugging Face (înainte de ordonare)
HTTP_TIMEOUT_SECONDS: float = 20  # cât așteptăm maxim după o sursă înainte să renunțăm la ea
CACHE_TTL_SECONDS: int = 60 * 60  # cât timp ținem minte rezultatele unei căutări (1 oră)

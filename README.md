# EMG Search

Motor de căutare specializat pe **electromiografie (EMG)**. Scrii un subiect (ex: `hand muscle`, `gesture recognition`, `fatigue`) și primești:

- **articole științifice** din [OpenAlex](https://openalex.org) și [Semantic Scholar](https://www.semanticscholar.org), unite într-o singură listă, fără dubluri, filtrate pe EMG;
- **seturi de date EMG** de pe [Hugging Face](https://huggingface.co/datasets).

Site-ul rulează pe calculatorul tău (sau pe un server pe care îl controlezi). Nu depinde de nicio platformă de hosting.

---

## 1. Instalare și pornire pe Windows (o singură dată)

Ai nevoie de:
- **Python 3.11 sau mai nou**, de pe [python.org](https://www.python.org/downloads/). La instalare, bifează **„Add python.exe to PATH”**.
- **VS Code** cu extensia **Python** (de la Microsoft).
- **Git**, de pe [git-scm.com](https://git-scm.com/download/win), dacă vrei să urci proiectul pe GitHub.

Deschide folderul proiectului în VS Code (`File → Open Folder`), apoi deschide un terminal (`Terminal → New Terminal`). Pe Windows, terminalul implicit e PowerShell. Rulează pe rând:

```powershell
# 1. Creează mediul virtual (un folder .venv cu un Python separat doar pentru acest proiect)
python -m venv .venv

# 2. Activează-l (după asta, în stânga liniei de comandă apare "(.venv)")
.venv\Scripts\Activate.ps1

# 3. Instalează bibliotecile din requirements.txt în mediul virtual
pip install -r requirements.txt

# 4. Creează fișierul de configurare (cheile API sunt opționale, vezi secțiunea 4)
copy .env.example .env
```

> Dacă la pasul 2 apare o eroare de tip *„running scripts is disabled on this system”*, rulează o dată
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, confirmă cu `Y`, apoi reia pasul 2.

În VS Code: `Ctrl+Shift+P` → **Python: Select Interpreter** → alege interpretorul din `.venv`. Așa, editorul folosește același Python ca proiectul.

### Pornirea site-ului (de fiecare dată)

```powershell
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Deschide în browser: **http://127.0.0.1:8000**

- `--reload` repornește automat serverul când salvezi un fișier, deci vezi modificările imediat.
- Oprești serverul cu `Ctrl+C` în terminal.
- **http://127.0.0.1:8000/docs** este pagina de documentație automată a API-ului JSON, unde poți testa căutări direct.

### Rularea testelor

```powershell
pytest
```

Testele verifică logica (eliminarea dublurilor, filtrul EMG, filtrele de an etc.) fără să acceseze internetul. Rulează-le după fiecare modificare. Dacă un test pică, ai stricat ceva ce mergea înainte.

---

## 2. Cum funcționează (drumul unei căutări)

```
 Browser                     Serverul tău (Python / FastAPI)                 Platforme externe
 ───────                     ─────────────────────────────────               ─────────────────
 scrii "hand muscle"  ──►  app/main.py   primește cererea /?q=hand muscle
                              │
                              ▼
                           app/search.py  search_all()
                              │  1. e în cache? → răspunde direct
                              │  2. întreabă TOATE sursele în PARALEL  ───►  api.openalex.org
                              │                                         ───►  api.semanticscholar.org
                              │                                         ───►  huggingface.co/api
                              │  3. fiecare app/sources/*.py traduce JSON-ul primit
                              │     în clasele comune din app/models.py (Article, Dataset)
                              │  4. unește dublurile (după DOI sau titlu)
                              │  5. păstrează doar articolele despre EMG
                              ▼
                           app/main.py  aplică filtrele (ani, open access, ordonare)
                              │
                              ▼
 vezi rezultatele   ◄──   app/templates/index.html  completat cu datele (Jinja2) + app/static/style.css
```

### Ce e un API și cum „ne conectăm”
Un API web este o adresă la care trimiți o cerere și primești înapoi date (de obicei JSON). Pentru noi, cererea e practic un link. Poți încerca în browser:

```
https://api.openalex.org/works?filter=title_and_abstract.search:hand muscle electromyography&per_page=2
```

Codul nostru face același lucru, din Python, cu biblioteca `httpx`. Nu există nicio „integrare” mai complicată de atât.

### Cum se limitează căutarea la EMG
- **OpenAlex** înțelege operatori logici, așa că trimitem `(ce ai scris tu) AND (electromyography OR EMG OR sEMG OR myoelectric)` și căutăm doar în titlu și rezumat.
- **Semantic Scholar** nu înțelege AND/OR, așa că adăugăm cuvântul `electromyography` la căutare, apoi verificăm noi fiecare rezultat: păstrăm doar articolele care au un termen EMG în titlu sau rezumat.
- **Hugging Face** caută doar în numele seturilor de date. De aceea aducem toate seturile care au „emg”, „electromyograph”, „myoelectric” sau „ninapro” în nume, apoi le ordonăm după câte cuvinte din căutarea ta apar în nume, descriere și etichete.

---

## 3. Harta fișierelor: unde modifici ce

| Vrei să... | Fișierul |
|---|---|
| schimbi termenii care definesc „EMG”, câte rezultate se cer, timpul de cache | `app/config.py` |
| schimbi cum se caută pe OpenAlex / Semantic Scholar / Hugging Face | `app/sources/openalex.py`, `semantic_scholar.py`, `huggingface.py` |
| adaugi o sursă nouă (ex: PubMed, arXiv) | creezi `app/sources/<nume>.py` după modelul celorlalte, apoi o adaugi în `ARTICLE_SOURCES` din `app/search.py` |
| schimbi cum se unesc dublurile, filtrul EMG, ordonarea | `app/search.py` |
| adaugi un câmp nou la articol (ex: cuvinte cheie) | `app/models.py`, apoi îl completezi în fiecare sursă și îl afișezi în șablon |
| adaugi o pagină sau un parametru nou în URL | `app/main.py` |
| schimbi ce apare pe pagină | `app/templates/index.html` |
| schimbi culori, fonturi, spațieri | `app/static/style.css` (culorile sunt variabile la începutul fișierului) |
| adaugi teste | `tests/test_search.py` |
| adaugi o bibliotecă Python | o adaugi în `requirements.txt`, apoi rulezi `pip install -r requirements.txt` |

Restul fișierelor:
- `.env.example`: modelul fișierului de configurare. `.env` (copia ta) conține cheile și **nu se urcă pe GitHub**.
- `.gitignore`: lista fișierelor pe care Git le ignoră (`.venv`, `.env`, cache-uri).
- `pytest.ini`: configurarea testelor.

---

## 4. Cheile API (opționale, dar recomandate)

Site-ul merge fără chei, dar cu limite:

| Sursă | Fără cheie | Cu cheie (gratuită) |
|---|---|---|
| **OpenAlex** | O cotă zilnică mică, împărțită cu toți cei de pe aceeași adresă IP. Fiecare cerere are un cost (căutarea: ~0.001 USD din cota gratuită). | Cotă proprie, mult mai mare. Cheia se obține din contul de pe openalex.org. |
| **Semantic Scholar** | Refuză des cererile (eroare 429), pentru că toți utilizatorii fără cheie împart aceeași limită. Site-ul afișează un mesaj și continuă cu celelalte surse. | Limită proprie. Se cere aici: https://www.semanticscholar.org/product/api#api-key-form |
| **Hugging Face** | Merge fără probleme pentru seturile de date publice. | Nu e nevoie. |

Cheile le pui în fișierul `.env`:
```
OPENALEX_API_KEY=cheia_ta
SEMANTIC_SCHOLAR_API_KEY=cheia_ta
```
Repornește apoi serverul. **Nu pune niciodată cheile direct în cod și nu urca `.env` pe GitHub.**

> Condițiile de utilizare ale platformelor se pot schimba. Dacă o sursă începe să dea erori, verifică documentația ei:
> [OpenAlex](https://docs.openalex.org) · [Semantic Scholar](https://api.semanticscholar.org/api-docs/) · [Hugging Face](https://huggingface.co/docs/hub/api).

---

## 5. Urcarea pe GitHub

1. Creează pe github.com un repository nou, **gol** (fără README), de exemplu `emg-search`. Îl poți face **Private**.
2. În terminalul din VS Code, în folderul proiectului:

```powershell
git init
git add .
git commit -m "Prima versiune EMG Search"
git branch -M main
git remote add origin https://github.com/<utilizatorul-tau>/emg-search.git
git push -u origin main
```

Înainte de commit, verifică cu `git status` că **`.env` și `.venv` NU apar** în listă (`.gitignore` le exclude).

---

## 6. Accesul colegilor (mai târziu)

Acum site-ul e accesibil doar de pe calculatorul tău (`127.0.0.1` = „acest calculator”). Ca să-l folosească și colegii, în ordinea complexității:

1. **În aceeași rețea (ex: rețeaua facultății):** pornește cu `uvicorn app.main:app --host 0.0.0.0 --port 8000`. Colegii intră la `http://<IP-ul-calculatorului-tău>:8000`. S-ar putea să trebuiască permis portul în Windows Firewall. Merge doar cât timp calculatorul tău e pornit.
2. **Pe un server al facultății/laboratorului (recomandat):** cereți un server Linux, copiați proiectul, rulați același `uvicorn` în spatele unui server web ca **Caddy** sau **nginx** (pentru HTTPS și un nume de domeniu). Opțional, totul poate fi pus într-un container **Docker**.

În ambele cazuri tu controlezi codul și serverul. Nu e o platformă care îți hostează site-ul printr-un wizard.

---

## 7. Idei pentru pașii următori

- Cache permanent în **SQLite** (acum cache-ul e în memorie și se pierde la repornire).
- Export rezultate în **CSV / BibTeX** (pentru referințe în lucrări).
- Încă o sursă de articole: **PubMed** (foarte relevantă pentru EMG clinic) sau **arXiv**.
- Modele ML EMG de pe Hugging Face (`/api/models`), pe lângă seturile de date.
- Paginare (acum se aduc primele 25 de rezultate din fiecare sursă).

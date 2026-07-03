ISTRUZIONI RAPIDE

1) Crea un nuovo repository GitHub vuoto.
2) Carica SOLO questi file nella pagina principale del repository:
   - app.py
   - requirements.txt
   - Procfile
   - .gitignore
   - README_PRIMA_LEGGIMI.txt

NON caricare lo ZIP e NON creare cartelle.
NON usare render.yaml.

3) Su Render crea prima un database PostgreSQL Free.
4) Poi crea un Web Service collegato al nuovo repository.

Impostazioni Render Web Service:
- Runtime: Python 3
- Branch: main
- Build Command: pip install -r requirements.txt
- Start Command: gunicorn app:app
- Instance Type: Free

Environment Variables:
- SECRET_KEY = GestionaleCasa2026!#
- DATABASE_URL = incolla la Internal Database URL del database PostgreSQL Render

Login iniziale del gestionale:
- username: admin
- password: admin123

IMPORTANTE:
Render Free non mantiene salvati in modo permanente i file caricati nella cartella uploads.
Il database invece resta su PostgreSQL. Per foto e documenti permanenti serve in seguito uno storage esterno.

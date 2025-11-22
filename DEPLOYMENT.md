# Návod k nasazení UctoAppka

## Lokální vývoj

1. Vytvořte virtuální prostředí:
```bash
python -m venv venv
source venv/bin/activate  # Na Windows: venv\Scripts\activate
```

2. Nainstalujte závislosti:
```bash
pip install -r requirements.txt
```

3. Spusťte migrace:
```bash
python manage.py migrate
```

4. Vytvořte uživatele:
```bash
python manage.py create_users
```

5. Vytvořte superuživatele pro admin rozhraní (volitelné):
```bash
python manage.py createsuperuser
```

6. Spusťte vývojový server:
```bash
python manage.py runserver
```

Aplikace bude dostupná na http://127.0.0.1:8000/

## Nasazení na produkci

### Důležité bezpečnostní kroky:

1. **Nastavte SECRET_KEY**:
   - Vytvořte silný, náhodný SECRET_KEY
   - Nastavte ho jako environment variable: `export SECRET_KEY='your-secret-key-here'`

2. **Nastavte DEBUG=False**:
   - V produkci musí být `DEBUG=False`
   - Nastavte: `export DEBUG=False`

3. **Nastavte ALLOWED_HOSTS**:
   - Přidejte vaši doménu: `export ALLOWED_HOSTS='yourdomain.com,www.yourdomain.com'`

4. **Nastavte databázi**:
   - SQLite je vhodné pro malé aplikace (výchozí)
   - Pro větší zátěž můžete použít MySQL (dostupné na PythonAnywhere)

5. **Sběr statických souborů**:
```bash
python manage.py collectstatic --noinput
```

### Nasazení na PythonAnywhere:

1. **Vytvořte účet na PythonAnywhere:**
   - Zaregistrujte se na https://www.pythonanywhere.com
   - Zvolte bezplatný nebo placený plán

2. **Nahrajte kód:**
   - Použijte Git (doporučeno):
     ```bash
     git clone https://github.com/yourusername/UctoAppka.git
     ```
   - Nebo nahrajte soubory přes Files tab v PythonAnywhere dashboardu

3. **Nastavte virtuální prostředí:**
   - V Bash konzoli:
     ```bash
     cd ~/UctoAppka  # nebo cesta k vašemu projektu
     python3.10 -m venv venv  # nebo python3.11 podle dostupnosti
     source venv/bin/activate
     pip install -r requirements.txt
     ```

4. **Nastavte WSGI konfiguraci:**
   - V PythonAnywhere dashboardu přejděte na **Web** tab
   - Klikněte na **WSGI configuration file**
   - Nahraďte obsah tímto:
     ```python
     import os
     import sys
     
     path = '/home/yourusername/UctoAppka'  # upravte na vaši cestu
     if path not in sys.path:
         sys.path.append(path)
     
     os.environ['DJANGO_SETTINGS_MODULE'] = 'uctoappka.settings'
     
     from django.core.wsgi import get_wsgi_application
     application = get_wsgi_application()
     ```

5. **Nastavte environment variables:**
   - V **Web** tabu, sekce **Environment variables**, přidejte:
     - `SECRET_KEY`: váš tajný klíč
     - `DEBUG`: `False`
     - `ALLOWED_HOSTS`: `yourusername.pythonanywhere.com`

6. **Nastavte statické soubory:**
   - V **Web** tabu, sekce **Static files**:
     - URL: `/static/`
     - Directory: `/home/yourusername/UctoAppka/staticfiles`

7. **Spusťte migrace a vytvořte uživatele:**
   - V Bash konzoli:
     ```bash
     source venv/bin/activate
     cd ~/UctoAppka
     python manage.py migrate
     python manage.py collectstatic --noinput
     python manage.py create_users
     ```

8. **Nastavte webovou aplikaci:**
   - V **Web** tabu:
     - Source code: `/home/yourusername/UctoAppka`
     - Working directory: `/home/yourusername/UctoAppka`
     - Python version: vyberte verzi, kterou používáte (3.10 nebo 3.11)
     - Virtualenv: `/home/yourusername/UctoAppka/venv`

9. **Reload webové aplikace:**
   - Klikněte na zelené tlačítko **Reload** v **Web** tabu

10. **Aplikace by měla být dostupná na:**
    - `https://yourusername.pythonanywhere.com`

### Poznámky pro PythonAnywhere:

- **Bezplatný plán:** Aplikace se "usíná" po nečinnosti, první načtení může trvat déle
- **Placený plán:** Aplikace běží nepřetržitě
- **Databáze:** SQLite je vhodné pro začátek, pro větší zátěž zvažte MySQL (dostupné na PythonAnywhere)
- **Zálohy:** Pravidelně zálohujte `db.sqlite3` soubor
- **SSL:** PythonAnywhere poskytuje HTTPS automaticky pro všechny domény

### Bezpečnostní doporučení:

1. **Změňte výchozí hesla uživatelů** po prvním přihlášení
2. **Použijte silná hesla** pro všechny účty
3. **Pravidelně aktualizujte závislosti**: `pip install --upgrade -r requirements.txt`
4. **Zálohujte databázi** pravidelně
5. **Použijte HTTPS** v produkci (SSL certifikát)
6. **Omezte přístup k admin rozhraní** (např. pomocí IP whitelistingu)

### Poznámky:

- Aplikace je navržena pro 2 uživatele (jak je uvedeno v README)
- Všechny transakce vyžadují schválení (approved field)
- SQLite databáze je v souboru `db.sqlite3` - zálohujte ji pravidelně


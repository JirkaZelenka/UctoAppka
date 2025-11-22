# Rychlý návod pro nasazení na PythonAnywhere

## Krok za krokem

### 1. Příprava na PythonAnywhere

1. Zaregistrujte se na https://www.pythonanywhere.com
2. Vytvořte nový Bash konzoli (v **Consoles** tabu)

### 2. Nahrání kódu

**Možnost A - Git (doporučeno):**
```bash
cd ~
git clone https://github.com/yourusername/UctoAppka.git
cd UctoAppka
```

**Možnost B - Ruční nahrání:**
- Použijte **Files** tab v dashboardu
- Nahrajte všechny soubory projektu

### 3. Nastavení virtuálního prostředí

```bash
cd ~/UctoAppka
python3.10 -m venv venv  # nebo python3.11
source venv/bin/activate
pip install --user -r requirements.txt
```

### 4. Nastavení databáze

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py create_users
```

### 5. Konfigurace webové aplikace

1. Přejděte na **Web** tab v dashboardu
2. Klikněte na **Add a new web app**
3. Vyberte **Manual configuration** → **Python 3.10** (nebo 3.11)
4. Klikněte na **Next**

### 6. WSGI konfigurace

1. V **Web** tabu klikněte na odkaz **WSGI configuration file**
2. Nahraďte celý obsah tímto kódem (upravte cestu):

```python
import os
import sys

# Cesta k vašemu projektu
path = '/home/yourusername/UctoAppka'
if path not in sys.path:
    sys.path.append(path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'uctoappka.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

**⚠️ DŮLEŽITÉ:** Nahraďte `yourusername` vaším PythonAnywhere uživatelským jménem!

### 7. Environment variables

V **Web** tabu, sekce **Environment variables**, přidejte:

- `SECRET_KEY`: vygenerujte silný klíč (např. pomocí `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`)
- `DEBUG`: `False`
- `ALLOWED_HOSTS`: `yourusername.pythonanywhere.com`

### 8. Statické soubory

V **Web** tabu, sekce **Static files**:

- **URL:** `/static/`
- **Directory:** `/home/yourusername/UctoAppka/staticfiles`

### 9. Nastavení Source code a Working directory

V **Web** tabu:

- **Source code:** `/home/yourusername/UctoAppka`
- **Working directory:** `/home/yourusername/UctoAppka`

### 10. Reload aplikace

Klikněte na zelené tlačítko **Reload** v **Web** tabu.

### 11. Hotovo! 🎉

Aplikace by měla být dostupná na:
- `https://yourusername.pythonanywhere.com`

## Údržba

### Aktualizace kódu (při použití Gitu):

```bash
cd ~/UctoAppka
git pull
source venv/bin/activate
pip install --user -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

Pak klikněte na **Reload** v **Web** tabu.

### Záloha databáze:

```bash
cd ~/UctoAppka
cp db.sqlite3 db.sqlite3.backup
```

### Vytvoření superuživatele:

```bash
cd ~/UctoAppka
source venv/bin/activate
python manage.py createsuperuser
```

## Řešení problémů

### Aplikace nefunguje:
1. Zkontrolujte **Error log** v **Web** tabu
2. Zkontrolujte, že všechny cesty jsou správné
3. Zkontrolujte, že environment variables jsou nastavené

### Statické soubory se nezobrazují:
1. Zkontrolujte, že `collectstatic` byl spuštěn
2. Zkontrolujte nastavení Static files v **Web** tabu
3. Zkontrolujte, že cesta k `staticfiles` je správná

### Chyby s importy:
1. Zkontrolujte, že virtuální prostředí je aktivní
2. Zkontrolujte, že všechny závislosti jsou nainstalované
3. Zkontrolujte cestu v WSGI konfiguraci

## Bezpečnost

- ✅ Změňte výchozí hesla uživatelů (`user1` a `user2`)
- ✅ Použijte silný `SECRET_KEY`
- ✅ Nastavte `DEBUG=False` v produkci
- ✅ PythonAnywhere automaticky poskytuje HTTPS


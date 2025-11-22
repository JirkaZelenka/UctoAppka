# Rychlý start - UctoAppka

## Instalace a spuštění

1. **Vytvořte virtuální prostředí:**
```bash
python -m venv venv
```

2. **Aktivujte virtuální prostředí:**
   - Windows: `venv\Scripts\activate`
   - Linux/Mac: `source venv/bin/activate`

3. **Nainstalujte závislosti:**
```bash
pip install -r requirements.txt
```

4. **Spusťte migrace databáze:**
```bash
python manage.py migrate
```

5. **Vytvořte dva uživatelské účty:**
```bash
python manage.py create_users
```
Tím se vytvoří dva uživatelé:
- `user1` s heslem `change_me_123`
- `user2` s heslem `change_me_123`

**⚠️ DŮLEŽITÉ: Změňte hesla po prvním přihlášení!**

6. **Vytvořte superuživatele pro admin (volitelné):**
```bash
python manage.py createsuperuser
```

7. **Spusťte vývojový server:**
```bash
python manage.py runserver
```

8. **Otevřete prohlížeč:**
   - Aplikace: http://127.0.0.1:8000/
   - Admin: http://127.0.0.1:8000/admin/

## První kroky

1. Přihlaste se pomocí `user1` nebo `user2`
2. Vytvořte kategorie a subkategorie v sekci **Nastavení**
3. Začněte přidávat transakce v sekci **Přidat transakci**
4. Prohlížejte statistiky a dashboard

## Bezpečnost pro produkci

Před nasazením na produkci:

1. Nastavte `SECRET_KEY` jako environment variable
2. Nastavte `DEBUG=False`
3. Nastavte `ALLOWED_HOSTS` na vaši doménu
4. Změňte výchozí hesla uživatelů
5. Použijte HTTPS/SSL

Více informací v `DEPLOYMENT.md`


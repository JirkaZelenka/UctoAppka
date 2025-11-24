# UctoAppka
22.11.2025
- navázání na předchozí nástřel 04/2025, který ale neměl repo a nepoužíval cursor

Základní setup:
- aplikace v Django
- Sqlite DB
- administrace na zakládání a spravování účtů
- účty pro 2 lidi
- hlavní menu se záložkami
- securita důležitá - access jen přes dva vytvořené účty
- grafy - plotly? jiné interaktivní zborazení

Funkce (jednotlivé stránky):
Přidávání výdajů
    - částka
    - popis
    - typ (příjem, výdaj, investice = přesuny)
    - kategorie + subkategorie
    - u typu výdaj - na kolik je měsíců (typicky roční předplatné). Default = 0, tedy jednorázové
    - datum (defualt dnes)
    - datum a čas zapsání (automaticky)
    - datum a čas editace (až při další úpravě)
    - Kdo zapsal (default za sebe)
    - za koho placeno (default za sebe, ale může být i SPOLECNY UCET)
    - poznámka
    - APPROVED (nelze hned, musí být později approvnuto)

Editace vádajů
    - editace čehokoliv
    - možnost Approve výdajů

Dashboard měsíční
    - stránka s posledními zapsanými/editovanými položkami + filtry, jako dashboard
    - Jednoduchý přehled za kalendářní měsíc / poslendích 30 dní (toggle button) příjmy vs výdaje

Dlouhodobé statisiky
    - interaktivní grafy
    - měsíce po sobě - příjmy, výdaje, čístý příjem, investice (filtry)
    - koláčový rozpad výdajů na kategorie nebo subkategorie (filtry)
    - celkové čisté jmení graf

Predikce a očekávané výdaje
    - očekávaný příjem, ořekávané výdaje (na základě hodnot minulých měsíců a podle opakujících se předplatných)
    - možnost nastacení limitů a warningů při překročení
    - ?? AI - návrhy na úspory

Seznam trvalých plateb
    - předplatná časopisů
    - předplacené online služby
    - telefon, nájem, ...

Přehled investic
    - nainvestované částky
    - možnost doplnit aktuální hodnotu stavu investice

Settings
    - možnost editovat nabízené Kategorie a subkategorie
    - vylistování položek co jsou zpětně nekompatibilní s novými kategoriemi
    - hledání anomálií - příliš vysoké položky, neodpovídající částky pro svou kategorii


TODO:
- upravit aby podle typu transakce to některá pole nevyplnilo/ vyplnilo jinak
- udělat všechny transackce exportovatelné do excelu, a naopak umět nahrát excel, zpracovat, a vyřešit konflikty

- časem stránka hypotéky
- pracovat s výchozím stavem = přidat tam jednotlivé účty lidí, jak investice, tak osobko+spořák jakoby (+ hypo?/nemovitost?)
- respektive jeden úhel pohledu = Příjmy a Výdaje a Investice,
- druhý úhel jsou samotné investice a jejich stav
- třetí úhel je stav majetku, což se může a nemusí přímo odvíjet od příjmů a výdajů + růstu investic

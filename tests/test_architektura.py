"""Testy struktury warstwowej.

Podział na warstwy jest wart tyle, ile jego przestrzeganie. Bez kontroli
zależności po kilku tygodniach warstwa domenowa zaczyna importować Flaska,
a dostęp do bazy trafia z powrotem do tras — i zostaje sama nazwa katalogów.

Zależności mają biec w jedną stronę:

    api  ->  domain,  data,  security
    data ->  (tylko baza)
    domain -> nic z aplikacji
"""

import ast
import pathlib

import pytest

pytestmark = pytest.mark.unit

KATALOG_APLIKACJI = pathlib.Path(__file__).resolve().parent.parent / "app"


def _importy(sciezka: pathlib.Path):
    """Nazwy modułów importowanych przez plik."""
    drzewo = ast.parse(sciezka.read_text(encoding="utf-8"), filename=str(sciezka))
    nazwy = []
    for wezel in ast.walk(drzewo):
        if isinstance(wezel, ast.Import):
            nazwy += [a.name for a in wezel.names]
        elif isinstance(wezel, ast.ImportFrom) and wezel.module:
            nazwy.append(wezel.module)
    return nazwy


def _pliki(warstwa: str):
    return sorted((KATALOG_APLIKACJI / warstwa).glob("*.py"))


def test_struktura_warstw_istnieje():
    for warstwa in ("api", "domain", "data", "security"):
        assert (KATALOG_APLIKACJI / warstwa).is_dir(), f"Brak warstwy {warstwa}"


@pytest.mark.parametrize("plik", _pliki("domain"), ids=lambda p: p.name)
def test_domena_nie_zalezy_od_reszty_aplikacji(plik):
    """Reguły biznesowe muszą dać się testować bez bazy i bez HTTP.

    To warstwa, która przetrwa zmianę frameworka albo bazy danych.
    """
    zabronione = [i for i in _importy(plik)
                  if i.startswith(("app.api", "app.data", "app.security", "flask"))]
    assert not zabronione, f"{plik.name} zależy od {zabronione}"


@pytest.mark.parametrize("plik", _pliki("domain"), ids=lambda p: p.name)
def test_domena_nie_dotyka_bazy(plik):
    assert "sqlite3" not in _importy(plik), f"{plik.name} sięga do bazy danych"


@pytest.mark.parametrize("plik", _pliki("data"), ids=lambda p: p.name)
def test_warstwa_danych_nie_zalezy_od_warstwy_http(plik):
    """Zapytania nie mogą zależeć od tras — inaczej nie da się ich użyć
    z innego miejsca (np. ze skryptu) ani przetestować bez żądania."""
    zabronione = [i for i in _importy(plik) if i.startswith("app.api")]
    assert not zabronione, f"{plik.name} zależy od {zabronione}"


@pytest.mark.parametrize("plik", _pliki("api"), ids=lambda p: p.name)
def test_warstwa_http_nie_buduje_wlasnego_sql(plik):
    """SQL należy do warstwy danych.

    Zapytanie zbudowane w trasie omija miejsce, w którym pilnujemy granicy
    dostępu — a właśnie tam najłatwiej o wyciek cudzych zgłoszeń.
    """
    tresc = plik.read_text(encoding="utf-8").upper()
    for fraza in ("SELECT ", "INSERT INTO", "UPDATE ", "DELETE FROM"):
        assert fraza not in tresc, f"{plik.name} zawiera SQL ({fraza.strip()})"


def test_konfiguracja_jest_w_jednym_miejscu():
    """Zmienne środowiskowe czyta wyłącznie config.

    Wcześniej były rozproszone po czterech modułach i nie dało się
    odpowiedzieć na pytanie, czym w ogóle da się skonfigurować aplikację.
    """
    winowajcy = []
    for plik in KATALOG_APLIKACJI.rglob("*.py"):
        if plik.name == "config.py":
            continue
        if "os.environ" in plik.read_text(encoding="utf-8"):
            winowajcy.append(str(plik.relative_to(KATALOG_APLIKACJI)))
    assert not winowajcy, f"Konfiguracja czytana poza config.py: {winowajcy}"


def test_caly_kod_aplikacji_jest_w_repozytorium():
    """Każdy plik aplikacji musi być śledzony przez git.

    REGRESJA: wpis `.gitignore` o treści `data/` (bez ukośnika na początku)
    pasuje do KAŻDEGO katalogu o tej nazwie na dowolnym poziomie i po cichu
    wykluczył z repozytorium całą warstwę `app/data/`. Testy lokalnie
    przechodziły, bo pliki istniały na dysku — CI dostawało kod bez warstwy
    dostępu do bazy i nie startowało.

    Git nie ostrzega o takim pominięciu, więc pilnuje tego test.
    """
    import subprocess

    korzen = KATALOG_APLIKACJI.parent
    sledzone = subprocess.run(
        ["git", "ls-files", "app"],
        cwd=korzen, capture_output=True, text=True, check=True,
    ).stdout.split()
    sledzone = {pathlib.PurePosixPath(s) for s in sledzone}

    na_dysku = {
        pathlib.PurePosixPath(p.relative_to(korzen).as_posix())
        for p in KATALOG_APLIKACJI.rglob("*.py")
        if "__pycache__" not in p.parts
    }

    brakujace = sorted(str(p) for p in na_dysku - sledzone)
    assert not brakujace, (
        f"Pliki istnieja lokalnie, ale NIE trafily do repozytorium: {brakujace}. "
        f"Najczestsza przyczyna: zbyt ogolny wzorzec w .gitignore."
    )


def test_kazdy_modul_aplikacji_ma_opis():
    """Docstring modułu mówi, za co ta warstwa odpowiada."""
    bez_opisu = []
    for plik in KATALOG_APLIKACJI.rglob("*.py"):
        drzewo = ast.parse(plik.read_text(encoding="utf-8"), filename=str(plik))
        if not ast.get_docstring(drzewo):
            bez_opisu.append(str(plik.relative_to(KATALOG_APLIKACJI)))
    assert not bez_opisu, f"Moduły bez opisu: {bez_opisu}"

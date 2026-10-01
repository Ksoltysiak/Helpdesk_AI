# Kopie zapasowe i odtwarzanie bazy

Dane systemu (zgłoszenia, użytkownicy, ścieżka audytu) mieszczą się w jednym
pliku SQLite w wolumenie `helpdesk-data`. Wolumen chroni je przed restartem
kontenera, ale nie przed usunięciem wolumenu, uszkodzeniem dysku, błędną
migracją ani przypadkowym `docker compose down -v`. Te przypadki obsługuje
kontener `backup`.

## Jak to działa

| Element | Rola |
|---|---|
| `deploy/backup/Dockerfile` | Mały obraz Alpine: `sqlite3`, `bash`, `crond` |
| `deploy/backup/backup.sh` | Tworzy kopię, weryfikuje ją, usuwa najstarsze |
| `deploy/backup/restore.sh` | Odtwarza bazę z wybranej kopii |
| `deploy/backup/entrypoint.sh` | Uruchamia `crond` według harmonogramu |
| `deploy/backup/test-backup.sh` | Test pełnego cyklu odtwarzania (CI) |

Kontener startuje razem z resztą stosu (`docker compose up`) i podłącza ten
sam wolumen z bazą co aplikacja. Kopie trafiają do osobnego wolumenu
`helpdesk-backups` albo do katalogu hosta wskazanego przez `BACKUP_HOST_DIR`.

Każda kopia przechodzi przez te same kroki:

1. **Spójny zrzut przy działającej aplikacji.** Polecenie `.backup` używa
   Online Backup API SQLite. Zwykłe `cp` przy trybie WAL mogłoby skopiować
   plik bez ostatnich transakcji albo w trakcie zapisu.
2. **Kontrola spójności.** `PRAGMA integrity_check` na gotowej kopii. Kopia,
   której nie da się odtworzyć, jest gorsza niż jej brak, bo daje fałszywe
   poczucie bezpieczeństwa.
3. **Kompresja i suma kontrolna.** Plik `helpdesk-RRRRMMDD-GGMMSS.db.gz`
   (czas UTC) i obok niego `.sha256`, sprawdzany przy odtwarzaniu.
4. **Atomowe zapisanie.** Kopia powstaje pod nazwą tymczasową i dopiero na
   końcu jest przemianowywana. Przerwana kopia nigdy nie udaje najnowszej.
5. **Rotacja.** Zostaje `BACKUP_KEEP` najnowszych kopii.

Skrypty działają jako właściciel bazy, a nie jako root. SQLite w trybie WAL
tworzy obok bazy pliki `-wal` i `-shm`. Gdyby utworzył je root, aplikacja
(działająca bez uprawnień roota) nie mogłaby do nich pisać.

## Konfiguracja

Zmienne w pliku `.env` (wzór w `.env.example`):

| Zmienna | Domyślnie | Znaczenie |
|---|---|---|
| `BACKUP_SCHEDULE` | `0 2 * * *` | Harmonogram w składni crona (codziennie 2:00) |
| `BACKUP_KEEP` | `14` | Liczba przechowywanych kopii |
| `BACKUP_HOST_DIR` | wolumen `helpdesk-backups` | Katalog hosta na kopie |
| `TZ` | `Europe/Warsaw` | Strefa czasowa harmonogramu |

`BACKUP_HOST_DIR` warto ustawić na katalog **poza** repozytorium. Katalog
w repozytorium trafiłby do obrazu aplikacji przy `COPY . .`.

## Obsługa

Kopia na żądanie (np. przed aktualizacją):

```bash
docker compose exec backup backup.sh
```

Lista kopii:

```bash
docker compose exec backup restore.sh --list
```

Odtworzenie. Aplikacja musi być zatrzymana, bo podmiana pliku pod działającym
procesem zgubiłaby jego transakcje:

```bash
docker compose stop helpdesk
docker compose run --rm --no-deps backup restore.sh latest      # albo nazwa pliku
docker compose start helpdesk
```

`--no-deps` jest konieczne. Bez niego `compose run` uruchomiłby z powrotem
zależność, czyli aplikację. Dotychczasowa baza nie jest kasowana, tylko
zostaje obok jako `helpdesk.db.przed-odtworzeniem-<czas>`, więc pomyłkę przy
wyborze kopii da się cofnąć.

Przed podmianą `restore.sh` sprawdza sumę kontrolną i spójność kopii. Jeśli
któraś kontrola zawiedzie, obecna baza pozostaje nietknięta.

Logi zadań:

```bash
docker compose logs backup
```

## Weryfikacja

`deploy/backup/test-backup.sh` jest uruchamiany w CI na pełnym stosie
(zadanie „Pełny stos”). Sprawdza:

- utworzenie kopii na żądanie i poprawność sumy kontrolnej,
- że plik kopii nie należy do roota,
- **pełny scenariusz awarii**: usunięcie pliku bazy, odtworzenie z kopii,
  ponowny start aplikacji i ta sama liczba zgłoszeń co przed awarią,
- że aplikacja może **zapisywać** do odtworzonej bazy. Plik z niewłaściwym
  właścicielem dałby się czytać, a błąd wyszedłby dopiero przy pierwszym
  nowym zgłoszeniu,
- rotację (zostaje dokładnie `BACKUP_KEEP` kopii),
- odrzucenie uszkodzonej kopii bez naruszenia działającej bazy.

Lokalnie (przy uruchomionym stosie):

```bash
bash deploy/backup/test-backup.sh
```

## Ograniczenia

- **Kopie leżą na tym samym serwerze co baza.** Chronią przed błędem
  oprogramowania i człowieka, ale nie przed utratą całego hosta. Pełna
  ochrona wymaga kopii poza serwerem (np. synchronizacja `BACKUP_HOST_DIR`
  do magazynu obiektowego). To następny krok.
- **Punkt odtworzenia to ostatnia kopia.** Przy kopii co dobę można stracić
  do 24 godzin danych (RPO). Krótszy `BACKUP_SCHEDULE` zmniejsza to okno.
- **Sprawdzenie, czy aplikacja działa, jest przybliżone.** `restore.sh`
  odmawia, gdy istnieje niepusty plik `-wal`. Bezczynna aplikacja może go
  jednak nie mieć, więc zatrzymanie jej pozostaje obowiązkiem operatora.
- Po migracji na PostgreSQL `backup.sh` trzeba będzie przepisać na
  `pg_dump`. Harmonogram, rotacja, sumy kontrolne i test odtwarzania
  pozostają bez zmian.

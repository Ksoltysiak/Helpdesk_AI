"""Dostęp do danych użytkowników."""

from app.data.database import get_db

# Kolumny bezpieczne do wczytania w trakcie obsługi żądania. Hash hasła
# celowo poza listą — nie ma powodu, by krążył po aplikacji przy każdym
# uwierzytelnionym żądaniu.
KOLUMNY_PUBLICZNE = "id, username, name, role, email"


def po_id(uzytkownik_id):
    return get_db().execute(
        f"SELECT {KOLUMNY_PUBLICZNE} FROM users WHERE id = ?", (uzytkownik_id,)
    ).fetchone()


def po_nazwie_z_hasłem(username):
    """Pełny wiersz wraz z hashem — wyłącznie na potrzeby logowania."""
    return get_db().execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()

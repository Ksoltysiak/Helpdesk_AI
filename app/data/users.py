"""Dostęp do danych użytkowników."""

from app.data.database import get_db

# Kolumny bezpieczne do wczytania w trakcie obsługi żądania. Hash hasła
# celowo poza listą — nie ma powodu, by krążył po aplikacji przy każdym
# uwierzytelnionym żądaniu. Nazwa klienta dołączana jest złączeniem, bo
# interfejs pokazuje ją od razu po zalogowaniu.
KOLUMNY_PUBLICZNE = ("u.id, u.username, u.name, u.role, u.email,"
                     " u.client_id, c.name AS client_name")

_Z_KLIENTEM = "FROM users u LEFT JOIN clients c ON c.id = u.client_id"


def po_id(uzytkownik_id):
    return get_db().execute(
        f"SELECT {KOLUMNY_PUBLICZNE} {_Z_KLIENTEM} WHERE u.id = ?", (uzytkownik_id,)
    ).fetchone()


def po_nazwie_z_hasłem(username):
    """Pełny wiersz wraz z hashem — wyłącznie na potrzeby logowania."""
    return get_db().execute(
        f"SELECT {KOLUMNY_PUBLICZNE}, u.password {_Z_KLIENTEM} WHERE u.username = ?",
        (username,),
    ).fetchone()

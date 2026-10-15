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


def personel():
    """Technicy i kierownicy — osoby, którym można przypisać zgłoszenie."""
    return get_db().execute(
        "SELECT id, name, role FROM users WHERE role IN ('technik', 'kierownik')"
        " ORDER BY role = 'kierownik', name"
    ).fetchall()


def obslugiwani_klienci(technik_id):
    """Identyfikatory firm, które obsługuje technik."""
    return {r["client_id"] for r in get_db().execute(
        "SELECT client_id FROM technician_clients WHERE technician_id = ?", (technik_id,))}

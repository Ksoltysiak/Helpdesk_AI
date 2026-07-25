"""
Automatyczna kategoryzacja AI.

Obecna implementacja dziala lokalnie (dopasowanie slow kluczowych), wiec dziala
bez internetu, kluczy API i kosztow. Zwraca te sama strukture co model jezykowy:
{"kategoria": ..., "priorytet": ...}.

--- JAK PODLACZYC PRAWDZIWY MODEL (np. OpenAI) ---
Zamien cialo funkcji categorize() na wywolanie API:

    from openai import OpenAI
    client = OpenAI(api_key=...)

    def categorize(title, description):
        prompt = (
            "Skategoryzuj zgloszenie IT. Zwroc JSON z polami "
            "'kategoria' (jedna z: " + ", ".join(CATEGORIES) + ") oraz "
            "'priorytet' (Niski/Sredni/Wysoki/Krytyczny).\\n"
            f"Tytul: {title}\\nOpis: {description}"
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)

Reszta back-endu nie wymaga zmian — kontrakt funkcji pozostaje taki sam.
"""

CATEGORIES = [
    "Sprzet", "Oprogramowanie", "Siec", "Poczta",
    "Konta i dostep", "Bezpieczenstwo", "Peryferia",
]

SLA_HOURS = {"Krytyczny": 1, "Wysoki": 4, "Sredni": 8, "Niski": 24}

KEYWORDS = {
    "vpn": ("Siec", "Wysoki"),
    "serwer": ("Siec", "Krytyczny"),
    "internet": ("Siec", "Wysoki"),
    "wi-fi": ("Siec", "Sredni"),
    "wifi": ("Siec", "Sredni"),
    "siec": ("Siec", "Sredni"),
    "komputer": ("Sprzet", "Wysoki"),
    "laptop": ("Sprzet", "Sredni"),
    "monitor": ("Sprzet", "Sredni"),
    "ekran": ("Sprzet", "Wysoki"),
    "drukark": ("Peryferia", "Niski"),
    "skaner": ("Peryferia", "Niski"),
    "myszk": ("Peryferia", "Niski"),
    "klawiatur": ("Peryferia", "Niski"),
    "pendrive": ("Peryferia", "Niski"),
    "haslo": ("Konta i dostep", "Sredni"),
    "konto": ("Konta i dostep", "Sredni"),
    "logowan": ("Konta i dostep", "Sredni"),
    "uprawnien": ("Konta i dostep", "Sredni"),
    "outlook": ("Poczta", "Sredni"),
    "mail": ("Poczta", "Sredni"),
    "poczt": ("Poczta", "Sredni"),
    "phishing": ("Bezpieczenstwo", "Krytyczny"),
    "wirus": ("Bezpieczenstwo", "Krytyczny"),
    "malware": ("Bezpieczenstwo", "Krytyczny"),
    "ransomware": ("Bezpieczenstwo", "Krytyczny"),
    "wyludz": ("Bezpieczenstwo", "Krytyczny"),
    "wlaman": ("Bezpieczenstwo", "Krytyczny"),
    "licencj": ("Oprogramowanie", "Niski"),
    "zawiesz": ("Oprogramowanie", "Sredni"),
    "crash": ("Oprogramowanie", "Wysoki"),
    "erp": ("Oprogramowanie", "Krytyczny"),
}


# Kolejnosc wagi priorytetow — im wyzsza wartosc, tym pilniejsze zgloszenie.
_PRIORITY_RANK = {"Niski": 0, "Sredni": 1, "Wysoki": 2, "Krytyczny": 3}


def categorize(title, description):
    """Dopasowanie slow kluczowych z wyborem NAJPOWAZNIEJSZEGO trafienia.

    Zgloszenie czesto zawiera kilka slow kluczowych naraz (np. "phishing"
    i "haslo"). Zwracamy dopasowanie o najwyzszym priorytecie, aby incydent
    bezpieczenstwa nie zostal zaklasyfikowany jako rutynowa prosba o haslo
    i nie dostal lagodniejszego terminu SLA.
    """
    text = f"{title} {description}".lower()

    best = None
    for keyword, (category, priority) in KEYWORDS.items():
        if keyword in text:
            if best is None or _PRIORITY_RANK[priority] > _PRIORITY_RANK[best[1]]:
                best = (category, priority)

    if best is None:
        return {"kategoria": "Oprogramowanie", "priorytet": "Sredni"}
    return {"kategoria": best[0], "priorytet": best[1]}

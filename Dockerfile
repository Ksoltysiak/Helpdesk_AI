FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Kod zostaje własnością roota, a użytkownik aplikacji może pisać tylko do
# katalogu z bazą. Przejęty proces nie nadpisze wtedy plików .py.
# Zmiana właściciela samego /app/data (zamiast chown -R /app) nie kopiuje
# też całego kodu do nowej warstwy obrazu.
RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /app/data \
    && chown app:app /app/data \
    && chmod +x docker-entrypoint.sh

# Użytkownik aplikacji nie może pisać do katalogu z kodem, więc Python i tak
# nie zapisałby plików .pyc. Wyłączamy same próby.
ENV PYTHONDONTWRITEBYTECODE=1

USER app

EXPOSE 5000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "wsgi:app"]

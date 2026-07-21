FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/
COPY docker/docker-entrypoint.sh .

RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /app/data \
    && chown -R app:app /app \
    && chmod +x docker-entrypoint.sh

USER app

EXPOSE 5000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--chdir", "backend", "app:app"]

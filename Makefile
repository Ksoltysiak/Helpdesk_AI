.PHONY: help build up down restart seed test logs clean

help:
	@echo "Helpdesk AI - Dedykowane komendy deweloperskie i operacyjne"
	@echo ""
	@echo "  make build    - Buduje obraz kontenera backend i pobiera Nginx"
	@echo "  make up       - Uruchamia całe środowisko (web + backend) w tle"
	@echo "  make down     - Zatrzymuje i usuwa kontenery"
	@echo "  make restart  - Restartuje usługi w docker-compose"
	@echo "  make seed     - Wypełnia bazę danych danymi testowymi w kontenerze"
	@echo "  make test     - Uruchamia pakiet testów integracyjnych REST API"
	@echo "  make logs     - Wyświetla logi kontenerów w czasie rzeczywistym"
	@echo "  make clean    - Czyszczenie plików tymczasowych Python"

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

seed:
	docker compose exec backend python backend/seed.py

test:
	python scripts/demo.py

logs:
	docker compose logs -f

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

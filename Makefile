# Skróty najczęstszych poleceń. Każdy cel to zwykłe polecenie z README —
# Makefile niczego nie ukrywa, tylko oszczędza pisania.
#
# Windows: make jest m.in. w Git for Windows / MSYS2 / Chocolatey (choco install make).

ifeq ($(OS),Windows_NT)
PYTHON ?= py
else
PYTHON ?= python3
endif

COMPOSE       = docker compose
COMPOSE_HTTPS = docker compose -f docker-compose.yml -f docker-compose.https.yml

.DEFAULT_GOAL := help
.PHONY: help up down restart logs seed ps certs up-https down-https test e2e e2e-docker clean

help:
	@echo "Helpdesk AI - skroty polecen"
	@echo ""
	@echo "  Docker (HTTP, http://localhost:8080)"
	@echo "    make up          buduje i uruchamia stos (nginx + aplikacja) w tle"
	@echo "    make down        zatrzymuje stos"
	@echo "    make restart     restartuje uslugi"
	@echo "    make logs        logi na biezaco"
	@echo "    make ps          stan kontenerow i healthcheckow"
	@echo "    make seed        wypelnia baze danymi testowymi"
	@echo ""
	@echo "  Docker (HTTPS, https://localhost:8443)"
	@echo "    make certs       generuje samopodpisany certyfikat"
	@echo "    make up-https    uruchamia stos z TLS na nginx"
	@echo "    make down-https  zatrzymuje stos HTTPS"
	@echo ""
	@echo "  Testy"
	@echo "    make test        pytest z pokryciem kodu"
	@echo "    make e2e         demo.py na lokalnym serwerze (localhost:5000)"
	@echo "    make e2e-docker  demo.py przez nginx (localhost:8080)"
	@echo ""
	@echo "    make clean       usuwa __pycache__ i artefakty testow"

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

seed:
	$(COMPOSE) exec helpdesk python seed.py

certs:
	$(PYTHON) deploy/generate_ssl.py

up-https: certs
	$(COMPOSE_HTTPS) up -d --build

down-https:
	$(COMPOSE_HTTPS) down

test:
	$(PYTHON) -m pytest --cov --cov-report=term-missing

e2e:
	$(PYTHON) demo.py

e2e-docker:
	BASE_URL=http://localhost:8080 $(PYTHON) demo.py

# Python zamiast find/rm, żeby działało tak samo na Windowsie i Linuksie.
clean:
	$(PYTHON) -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path(\".\").rglob(\"__pycache__\")]; [shutil.rmtree(p, ignore_errors=True) for p in (\".pytest_cache\", \"htmlcov\")]; pathlib.Path(\".coverage\").unlink(missing_ok=True)"

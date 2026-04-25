.PHONY: help build up down restart logs shell dbshell test test-coverage format lint migrate makemigrations superuser loaddata load_practices load_practices_clear backup restore clean

# Variables
DOCKER_COMPOSE = docker-compose
SERVICE_WEB = web
SERVICE_DB = db

# Default target
.DEFAULT_GOAL := help

help: ## Show this help message
	@echo "LabControl Development Commands"
	@echo "================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Docker Commands
build: ## Build Docker images
	$(DOCKER_COMPOSE) build

up: ## Start all services
	$(DOCKER_COMPOSE) up -d

down: ## Stop all services
	$(DOCKER_COMPOSE) down

restart: ## Restart all services
	$(DOCKER_COMPOSE) restart

logs: ## View logs from all services
	$(DOCKER_COMPOSE) logs -f

logs-web: ## View logs from web service
	$(DOCKER_COMPOSE) logs -f $(SERVICE_WEB)

logs-db: ## View logs from database service
	$(DOCKER_COMPOSE) logs -f $(SERVICE_DB)

logs-backend: ## View logs from backend services (web + celery)
	$(DOCKER_COMPOSE) logs -f web celery_worker celery_beat

# ============================================================
# PROD log helpers — read docker logs on the VPS over SSH.
# All require DEPLOY_SSH_PASSWORD exported in your shell
# (see DEPLOYMENT.md §SSH Access). Examples:
#   make logs-prod                  # tail all backend services
#   make logs-prod-web              # tail only the web container
#   make logs-prod-worker           # tail celery_worker
#   make logs-prod-grep TERM=sync   # grep recent logs across containers
#   make logs-prod-errors           # only ERROR / WARNING lines
# ============================================================
SSH_PROD = sshpass -p "$$DEPLOY_SSH_PASSWORD" ssh -o StrictHostKeyChecking=accept-new deploy@72.60.137.226

logs-prod: ## VPS: tail web + celery_worker + celery_beat (Ctrl-C to exit)
	@$(SSH_PROD) "cd /opt/labcontrol && docker compose -f docker-compose.prod.yml logs -f --tail=100 web celery_worker celery_beat"

logs-prod-web: ## VPS: tail the web container only
	@$(SSH_PROD) "docker logs -f --tail=100 labcontrol_web"

logs-prod-worker: ## VPS: tail the celery_worker container
	@$(SSH_PROD) "docker logs -f --tail=100 labcontrol_celery_worker"

logs-prod-beat: ## VPS: tail the celery_beat container
	@$(SSH_PROD) "docker logs -f --tail=100 labcontrol_celery_beat"

logs-prod-nginx: ## VPS: tail nginx access + error logs
	@$(SSH_PROD) "docker logs -f --tail=100 labcontrol_nginx"

logs-prod-errors: ## VPS: show recent ERROR/WARNING lines across backend services
	@$(SSH_PROD) "cd /opt/labcontrol && docker compose -f docker-compose.prod.yml logs --tail=500 web celery_worker celery_beat 2>&1 | grep -E ' (ERROR|WARNING|EXCEPTION|FAILED|Traceback) '"

logs-prod-grep: ## VPS: grep recent logs (Usage: make logs-prod-grep TERM=sync_labwin)
	@if [ -z "$(TERM)" ]; then echo "Usage: make logs-prod-grep TERM=<pattern>"; exit 1; fi
	@$(SSH_PROD) "cd /opt/labcontrol && docker compose -f docker-compose.prod.yml logs --tail=2000 web celery_worker celery_beat 2>&1 | grep -i '$(TERM)'"

ps-prod: ## VPS: show container status with healthchecks
	@$(SSH_PROD) "cd /opt/labcontrol && docker compose -f docker-compose.prod.yml ps --format 'table {{.Name}}\t{{.Status}}'"

install-prod-logs-cli: ## VPS: install the `labcontrol-logs` shell wrapper to /usr/local/bin
	@sshpass -p "$$DEPLOY_SSH_PASSWORD" scp bin/labcontrol-logs deploy@72.60.137.226:/tmp/labcontrol-logs
	@$(SSH_PROD) "echo \"$$DEPLOY_SSH_PASSWORD\" | sudo -S install -m 755 /tmp/labcontrol-logs /usr/local/bin/labcontrol-logs && rm /tmp/labcontrol-logs && echo 'Installed. Run: labcontrol-logs --help'"

ps: ## Show running services
	$(DOCKER_COMPOSE) ps

# Django Commands
shell: ## Open Django shell
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) python manage.py shell

dbshell: ## Open database shell
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) python manage.py dbshell

migrate: ## Run database migrations
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) python manage.py migrate

makemigrations: ## Create new migrations
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) python manage.py makemigrations

showmigrations: ## Show migration status
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) python manage.py showmigrations

superuser: ## Create superuser (interactive)
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) python manage.py createsuperuser

create-superuser: ## Create superuser with email and password (Usage: make create-superuser EMAIL=test@test.com PASSWORD=123)
	@if [ -z "$(EMAIL)" ] || [ -z "$(PASSWORD)" ]; then \
		echo "Error: EMAIL and PASSWORD are required."; \
		echo "Usage: make create-superuser EMAIL=test@test.com PASSWORD=123"; \
		exit 1; \
	fi
	@echo "Creating superuser with email: $(EMAIL)"
	@$(DOCKER_COMPOSE) exec -T $(SERVICE_WEB) python manage.py shell <<< "from apps.users.models import User; User.objects.create_superuser(email='$(EMAIL)', password='$(PASSWORD)', first_name='Admin', last_name='User') if not User.objects.filter(email='$(EMAIL)').exists() else print('User already exists'); print('Superuser created successfully!' if not User.objects.filter(email='$(EMAIL)').exists() else 'User already exists')"

seed-users: ## Create seed users for development (admin, doctor, patient @labcontrol.com / test1234)
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) python manage.py create_seed_users

verify-email: ## Verify email for a user (Usage: make verify-email EMAIL=user@example.com)
	@if [ -z "$(EMAIL)" ]; then \
		echo "Error: EMAIL is required."; \
		echo "Usage: make verify-email EMAIL=user@example.com"; \
		exit 1; \
	fi
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) python manage.py verify_email $(EMAIL)

collectstatic: ## Collect static files
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) python manage.py collectstatic --noinput

setup-periodic-tasks: ## Setup Celery Beat periodic tasks
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) python manage.py setup_periodic_tasks

throttle-reset: ## Clear cache to reset API throttling
	@$(DOCKER_COMPOSE) exec -T $(SERVICE_WEB) python manage.py shell <<< "from django.core.cache import cache; cache.clear(); print('✓ Throttle cache cleared!')"

# Testing Commands
test: ## Run tests
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) bash -c "DJANGO_SETTINGS_MODULE=config.settings.test pytest"

test-coverage: ## Run tests with coverage report
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) bash -c "DJANGO_SETTINGS_MODULE=config.settings.test pytest --cov=apps --cov-report=html --cov-report=term"

test-watch: ## Run tests in watch mode
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) bash -c "DJANGO_SETTINGS_MODULE=config.settings.test ptw"

test-verbose: ## Run tests with verbose output
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) bash -c "DJANGO_SETTINGS_MODULE=config.settings.test pytest -v"

test-fast: ## Run tests without coverage
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) bash -c "DJANGO_SETTINGS_MODULE=config.settings.test pytest -q"

# Code Quality Commands
format: ## Format code with Black
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) black .

format-check: ## Check code formatting
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) black --check .

lint: ## Run linter (flake8)
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) flake8 .

isort: ## Sort imports
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) isort .

isort-check: ## Check import sorting
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) isort --check-only .

typecheck: ## Run type checking with mypy
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) mypy .

quality: format lint isort ## Run all code quality checks

# Database Commands
db-reset: ## Reset database (WARNING: Destroys all data!)
	$(DOCKER_COMPOSE) down -v
	$(DOCKER_COMPOSE) up -d $(SERVICE_DB)
	sleep 5
	$(DOCKER_COMPOSE) up -d $(SERVICE_WEB)
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) python manage.py migrate
	@echo "Database has been reset. Create a new superuser with 'make superuser'"

backup: ## Create database backup
	@mkdir -p backups
	$(DOCKER_COMPOSE) exec -T $(SERVICE_DB) pg_dump -U labcontrol_user labcontrol_db > backups/backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "Backup created in backups/ directory"

restore: ## Restore database from backup (Usage: make restore BACKUP_FILE=backup.sql)
	@if [ -z "$(BACKUP_FILE)" ]; then \
		echo "Error: BACKUP_FILE is required. Usage: make restore BACKUP_FILE=backup.sql"; \
		exit 1; \
	fi
	$(DOCKER_COMPOSE) exec -T $(SERVICE_DB) psql -U labcontrol_user labcontrol_db < $(BACKUP_FILE)
	@echo "Database restored from $(BACKUP_FILE)"

loaddata: ## Load fixture data
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) python manage.py loaddata fixtures/*.json

load_practices: ## Load practices from JSON file
	@echo "Loading practices from data/practices_data.json..."
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) python manage.py load_practices
	@echo "✓ Practices loaded successfully!"

load_practices_clear: ## Load practices (clear existing first)
	@echo "Loading practices (clearing existing data)..."
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) python manage.py load_practices --clear
	@echo "✓ Practices loaded successfully!"

# Celery Commands
celery-worker: ## Start Celery worker
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) celery -A config worker -l info

celery-beat: ## Start Celery beat
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) celery -A config beat -l info

flower: ## Start Flower (Celery monitoring)
	@echo "Flower is running at http://localhost:5555"
	$(DOCKER_COMPOSE) up -d flower

# Clean Commands
clean: ## Clean up temporary files and caches
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned up temporary files and caches"

clean-all: clean down ## Clean everything including Docker volumes
	$(DOCKER_COMPOSE) down -v
	@echo "Cleaned up everything including Docker volumes"

# Setup Commands
setup: build up migrate superuser ## Initial setup (build, migrate, create superuser)
	@echo "Setup complete! Access the app at http://localhost:8000"

rebuild: down build up migrate ## Rebuild and restart everything
	@echo "Rebuild complete!"

# Development Utilities
check: format-check lint isort-check test ## Run all checks (format, lint, tests)
	@echo "All checks passed!"

ci: check ## Run CI pipeline checks
	@echo "CI checks complete!"

install-dev: ## Install development dependencies locally
	pip install -r requirements/dev.txt

# Documentation
docs-serve: ## Serve documentation locally
	$(DOCKER_COMPOSE) exec $(SERVICE_WEB) sphinx-build -b html docs/ docs/_build/html
	@echo "Documentation built in docs/_build/html/"

# Health Check
health: ## Check health of all services
	@echo "Checking service health..."
	@$(DOCKER_COMPOSE) ps
	@echo "\nChecking web service..."
	@curl -f http://localhost:8000/admin/ > /dev/null 2>&1 && echo "✓ Web service is healthy" || echo "✗ Web service is not responding"
	@echo "\nChecking database..."
	@$(DOCKER_COMPOSE) exec $(SERVICE_DB) pg_isready -U labcontrol_user && echo "✓ Database is healthy" || echo "✗ Database is not responding"

# Git Hooks
pre-commit: format lint test ## Run pre-commit checks
	@echo "Pre-commit checks passed!"

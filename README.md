# LabControl Platform - Backend API

Production-grade Django REST API for multi-client medical laboratory management system.

## Overview

This is a scalable, secure backend system designed for handling medical studies, appointments, and patient data across multiple laboratory clients. Built with HIPAA compliance and PII protection in mind.

### Key Features

- Multi-tenant architecture for lab replication
- Secure medical data handling with encryption
- RESTful API with Django REST Framework
- Asynchronous task processing with Celery
- Real-time notifications
- Payment processing integration
- Comprehensive test coverage
- CI/CD ready with GitHub Actions
- Docker-based development and deployment

## Tech Stack

- **Backend**: Django 4.2 LTS (Python 3.11+)
- **API**: Django REST Framework
- **Authentication**: Django-allauth + JWT
- **Database**: PostgreSQL 15
- **Cache/Queue**: Redis
- **Task Queue**: Celery
- **Web Server**: Nginx (production)
- **Containerization**: Docker & Docker Compose
- **Cloud**: Google Cloud Platform (GCP)

## Project Structure

```
labcontrol/
├── apps/                       # Django applications
│   ├── users/                  # Custom user management & authentication
│   ├── studies/                # Medical studies & test results
│   ├── appointments/           # Scheduling & appointment management
│   ├── payments/               # Billing & payment processing
│   └── notifications/          # Email/SMS notifications
├── config/                     # Project configuration
│   ├── settings/               # Modular settings (base, dev, prod)
│   ├── urls.py                 # Root URL configuration
│   ├── wsgi.py                 # WSGI application
│   ├── asgi.py                 # ASGI application (for async)
│   └── celery.py               # Celery configuration
├── requirements/               # Python dependencies
│   ├── base.txt                # Core dependencies
│   ├── dev.txt                 # Development dependencies
│   └── prod.txt                # Production dependencies
├── tests/                      # Test suite
├── .github/workflows/          # CI/CD pipelines
├── docker-compose.yml          # Local development stack
├── Dockerfile                  # Production Docker image
├── Makefile                    # Development commands
└── manage.py                   # Django management script
```

## Prerequisites

- Docker Desktop (or Docker Engine + Docker Compose)
- Git
- Make (optional, but recommended)

## Quick Start

### 1. Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd labcontrol

# Copy environment variables
cp .env.example .env

# Review and update .env with your local settings
# For development, the defaults should work fine
```

### 2. Build and Run

```bash
# Build and start all services
make build
make up

# Or without Make:
docker-compose build
docker-compose up -d
```

### 3. Initialize Database

```bash
# Run migrations
make migrate

# Create superuser
make superuser

# Load sample data (optional)
make loaddata
```

### 4. Access the Application

- API: http://localhost:8000/api/v1/
- Admin Panel: http://localhost:8000/admin/
- API Documentation: http://localhost:8000/api/docs/

## Development Workflow

### Common Commands

```bash
# Start services
make up

# View logs
make logs

# Run tests
make test

# Run tests with coverage
make test-coverage

# Format code with Black
make format

# Run linter
make lint

# Create new migration
make makemigrations

# Apply migrations
make migrate

# Access Django shell
make shell

# Access database shell
make dbshell

# Stop all services
make down

# Rebuild services
make rebuild
```

### Manual Commands (without Make)

```bash
# Start services
docker-compose up -d

# Run tests
docker-compose exec web pytest

# Format code
docker-compose exec web black .

# Create migrations
docker-compose exec web python manage.py makemigrations

# Apply migrations
docker-compose exec web python manage.py migrate

# Access shell
docker-compose exec web python manage.py shell

# View logs
docker-compose logs -f web

# Stop services
docker-compose down
```

### Creating a New Django App

```bash
# Create new app in the apps/ directory
docker-compose exec web python manage.py startapp newapp apps/newapp

# Then:
# 1. Add 'apps.newapp' to INSTALLED_APPS in config/settings/base.py
# 2. Create models, serializers, views, and URLs
# 3. Run makemigrations and migrate
# 4. Write tests
```

### Running Tests

```bash
# Run all tests
make test

# Run specific test file
docker-compose exec web pytest tests/test_users.py

# Run with coverage report
make test-coverage

# Run tests in watch mode (great for TDD)
docker-compose exec web ptw
```

### Code Quality

This project uses:
- **Black** for code formatting (line length: 88)
- **Flake8** for linting
- **isort** for import sorting
- **mypy** for type checking (optional)

```bash
# Format all code
make format

# Run linter
make lint

# Run type checking
make typecheck
```

## Database Management

### Backups

```bash
# Create backup
make backup

# Restore from backup
make restore BACKUP_FILE=backup_2024_01_01.sql
```

### Migrations

```bash
# Create new migration
docker-compose exec web python manage.py makemigrations

# Apply migrations
docker-compose exec web python manage.py migrate

# Rollback migration
docker-compose exec web python manage.py migrate app_name 0001

# Show migration status
docker-compose exec web python manage.py showmigrations
```

## API Documentation

API documentation is auto-generated using drf-spectacular:

- **Swagger UI**: http://localhost:8000/api/docs/
- **ReDoc**: http://localhost:8000/api/redoc/
- **OpenAPI Schema**: http://localhost:8000/api/schema/

## Environment Variables

See `.env.example` for all available environment variables. Key settings:

- `DJANGO_SETTINGS_MODULE`: Settings module to use (dev/prod)
- `DJANGO_SECRET_KEY`: Secret key for cryptographic signing
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `SENTRY_DSN`: Sentry error tracking (production)

## Architecture Decisions

### Multi-App Structure

Following Domain-Driven Design, the project is organized into focused apps:
- Each app represents a bounded context
- Apps are loosely coupled and highly cohesive
- Shared utilities go in a `core` or `common` app

### Custom User Model

We use a custom user model from the start (`apps.users.User`) to:
- Allow email-based authentication
- Support multi-tenant features
- Add custom fields without migration headaches

### Modular Settings

Settings are split into:
- `base.py`: Common settings
- `dev.py`: Development-specific settings
- `prod.py`: Production-specific settings

This allows environment-specific configuration without code duplication.

### Celery for Background Tasks

Celery handles:
- Email notifications
- Report generation
- Data exports
- Scheduled tasks (appointment reminders, etc.)

### Security Considerations

- All PII is encrypted at rest
- HTTPS only in production
- CORS configured for frontend origins only
- Rate limiting on authentication endpoints
- SQL injection protection via ORM
- XSS protection via DRF serializers
- CSRF protection enabled

## Deployment

### Production Checklist

- [ ] Set `DJANGO_DEBUG=False`
- [ ] Use strong `DJANGO_SECRET_KEY` (50+ characters)
- [ ] Configure proper `ALLOWED_HOSTS`
- [ ] Set up PostgreSQL with backups
- [ ] Configure Redis persistence
- [ ] Set up GCS for file storage
- [ ] Configure HTTPS/SSL certificates
- [ ] Set up Sentry for error tracking
- [ ] Configure email service (SendGrid/Mailgun)
- [ ] Set up monitoring (GCP Monitoring/Prometheus)
- [ ] Configure log aggregation
- [ ] Run security scan
- [ ] Set up CI/CD pipeline
- [ ] Configure database backups
- [ ] Set up rate limiting

### Docker Deployment

```bash
# Build production image
docker build -t labcontrol-api:latest .

# Run with production settings
docker run -e DJANGO_SETTINGS_MODULE=config.settings.prod \
           -e DATABASE_URL=postgresql://... \
           -p 8000:8000 \
           labcontrol-api:latest
```

### GCP Deployment

Recommended GCP services:
- **Cloud Run**: For Django API containers
- **Cloud SQL**: For PostgreSQL
- **Cloud Storage**: For file uploads
- **Cloud Memorystore**: For Redis
- **Cloud Tasks**: Alternative to Celery for simple tasks
- **Cloud Build**: For CI/CD

## Testing

```bash
# Run all tests
make test

# Run with coverage
make test-coverage

# Run specific test
docker-compose exec web pytest tests/test_users.py::TestUserModel::test_create_user

# Run tests matching pattern
docker-compose exec web pytest -k "test_user"
```

### Test Coverage Goals

- Overall: >90%
- Critical paths (auth, payments): 100%
- Models: 100%
- Views/APIs: >95%

## Contributing

### Code Style

- Follow PEP 8
- Use Black for formatting (automated)
- Write docstrings for all public functions/classes
- Add type hints where appropriate
- Keep functions small and focused

### Commit Messages

Follow conventional commits:
```
feat: Add appointment reminder task
fix: Correct payment calculation
docs: Update deployment guide
test: Add user registration tests
refactor: Simplify study serializer
```

### Pull Request Process

1. Create feature branch from `develop`
2. Write tests for new features
3. Ensure all tests pass
4. Format code with Black
5. Update documentation
6. Submit PR with description
7. Wait for CI checks to pass
8. Request review

## Troubleshooting

### Common Issues

**Database connection errors:**
```bash
# Ensure database is running
docker-compose ps

# Check database logs
docker-compose logs db

# Recreate database
make db-reset
```

**Port already in use:**
```bash
# Change ports in docker-compose.yml or stop conflicting service
lsof -ti:8000 | xargs kill -9
```

**Permission errors:**
```bash
# Fix file permissions
sudo chown -R $USER:$USER .
```

**Migrations out of sync:**
```bash
# Reset migrations (CAUTION: Development only!)
make migrations-reset
```

## Support & Resources

- Documentation: [Link to docs]
- Issue Tracker: [Link to issues]
- Slack Channel: [Link to Slack]
- API Docs: http://localhost:8000/api/docs/

## License

[Your License Here]

## Onboarding Checklist for New Developers

- [ ] Install Docker Desktop
- [ ] Clone repository
- [ ] Copy `.env.example` to `.env`
- [ ] Run `make build && make up`
- [ ] Run `make migrate`
- [ ] Create superuser: `make superuser`
- [ ] Access admin panel and API docs
- [ ] Run test suite: `make test`
- [ ] Read architecture docs
- [ ] Set up IDE with Black formatter
- [ ] Join team Slack channel
- [ ] Review open issues
- [ ] Deploy to local environment
- [ ] Complete "Hello World" task (create simple API endpoint)

## Contact

For questions, contact the development team at dev@labcontrol.com

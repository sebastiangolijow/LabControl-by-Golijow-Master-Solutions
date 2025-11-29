# Contributing to LabControl

Thank you for your interest in contributing to LabControl! This document provides guidelines and instructions for contributing to the project.

## Development Setup

1. Fork and clone the repository
2. Copy `.env.example` to `.env` and configure
3. Run `make setup` to build and initialize the project
4. Create a new branch for your feature

## Code Style

We follow these conventions:

- **Python**: PEP 8 style guide
- **Formatting**: Black (line length: 88)
- **Import sorting**: isort
- **Linting**: Flake8
- **Type hints**: Encouraged but not required

Run code quality checks:
```bash
make format  # Format code with Black
make lint    # Check with Flake8
make isort   # Sort imports
```

## Testing

All new features must include tests:

```bash
make test              # Run all tests
make test-coverage     # Run with coverage report
make test-watch        # Run in watch mode
```

Test coverage requirements:
- Overall: >90%
- New features: 100%
- Critical paths (auth, payments): 100%

## Commit Messages

Follow conventional commits format:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Examples:
```
feat(users): add email verification
fix(payments): correct invoice calculation
docs(readme): update installation instructions
```

## Pull Request Process

1. Create a feature branch from `develop`
2. Make your changes
3. Write/update tests
4. Run all checks: `make check`
5. Commit with conventional commit messages
6. Push and create a pull request
7. Wait for CI checks to pass
8. Request review from maintainers

## Branch Naming

Use descriptive branch names:
- `feature/user-authentication`
- `fix/payment-calculation-bug`
- `docs/api-documentation`
- `refactor/study-model`

## Code Review Guidelines

Reviewers should check:
- [ ] Code follows style guidelines
- [ ] Tests are included and passing
- [ ] Documentation is updated
- [ ] No security vulnerabilities
- [ ] Performance considerations
- [ ] Database migrations are included if needed

## Questions?

Feel free to open an issue for discussion before starting major work.

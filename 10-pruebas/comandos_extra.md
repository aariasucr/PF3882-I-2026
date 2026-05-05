```bash

# flake8 linting
flake8 app/
flake8 *.py ./tests/

# pylint linting
pylint --generate-rcfile > .pylintrc
pylint app/

# Import sort
isort --check-only app/

# Check cyclomatic complexity
radon cc **/*.py -nc
radon cc **/*.py
radon cc app/

# Code formatter
black --check app/

# Auditar dependencias
pip-audit

# Static type checker
mypy app/

# Security scan
bandit -r app/
bandit -r app/ tests/
```

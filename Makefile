# Run all quality gates in one go
.PHONY: setup check cleanup-sessions

# Install dependencies before running checks
setup:
	@pip install -r requirements.txt
	@pip install -r dev-requirements.txt

check: setup
	black .
	isort .
	pytest --cov=src --cov-report=term-missing --cov-fail-under=80
	mypy src/
	bandit -r src/

cleanup-sessions:
	@python scripts/cleanup_sessions.py --retention-hours 168

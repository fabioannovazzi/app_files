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

# One canonical version per product; build both host distributions together.
.PHONY: release-products check-product-releases
release-products:
	python scripts/build_product_release.py

check-product-releases:
	python scripts/build_product_release.py --check

# Native Cowork evidence is supplied explicitly; CI/shell tests cannot create it.
.PHONY: check-cowork-acceptance
check-cowork-acceptance:
	@test -n "$(COWORK_ACCEPTANCE_RUN)" || (echo "Set COWORK_ACCEPTANCE_RUN to the inspected bundle" >&2; exit 1)
	python scripts/cowork_acceptance/cowork_acceptance.py verify "$(COWORK_ACCEPTANCE_RUN)" --require-core-passed

PYTHON ?= .venv/bin/python

.PHONY: install test-projects test-capstone

install:
	uv pip install --python $(PYTHON) -r requirements.txt

test-projects:
	$(PYTHON) scripts/verify_all_projects.py

test-capstone:
	$(PYTHON) -m pytest project_iterations/day_62/tests project_iterations/day_63/tests project_iterations/day_64/tests project_iterations/day_65/tests project_iterations/day_66/tests project_iterations/day_67/tests project_iterations/day_68/tests project_iterations/day_69/tests project_iterations/day_70/tests -v

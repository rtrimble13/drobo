.PHONY: build install test fmt clean help

# Default target
help:
	@echo "Available targets:"
	@echo "  build    - Build the project"
	@echo "  install  - Install the project"
	@echo "  test     - Run unit tests using pytest framework"
	@echo "  fmt      - Run linting checks with black, flake8 and isort"
	@echo "  clean    - Clean build and dist output"
	@echo "  help     - Show this help message"

build:
	python -m build

install:
	pip install -e .[dev]

test:
	PYTHONPATH=src python -m pytest test/ -v

fmt:
	PYTHONPATH=src python -m black src/ test/
	PYTHONPATH=src python -m isort src/ test/
	PYTHONPATH=src python -m flake8 src/ test/ --max-line-length=88

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf src/*.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
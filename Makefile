.PHONY: build install test fmt clean help doc dist

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
	@echo "Creating/using conda env 'drobo' and installing dev dependencies"
	@if command -v conda >/dev/null 2>&1; then \
		if ! conda env list | awk '{print $$1}' | grep -qx drobo; then \
			echo "Creating conda env 'drobo'..."; \
			conda create -n drobo python=3.13 -y; \
		else \
			echo "Conda env 'drobo' already exists"; \
		fi; \
		echo "Installing editable package info 'drobo'..."; \
		conda run -n drobo python -m pip install -e .[dev]; \
	else \
		echo "conda not found, falling back to system pip"; \
		python -m pip install -e .[dev]; \
	fi

install:
	python -m pip install .

test:
	python -m pytest test/ -v

fmt:
	python -m black src/ test/
	python -m isort src/ test/
	python -m flake8 src/ test/ --max-line-length=80

doc:
	@echo "Documentation target - build man files <todo>"
	@mkdir -p doc/man

dist:
	python -m pip install --upgrade build
	python -m build

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf src/*.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

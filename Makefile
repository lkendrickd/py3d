# Variables
VENV_DIR = venv
PYTHON = python3
PIP = $(VENV_DIR)/bin/pip
PYTHON_VENV = $(VENV_DIR)/bin/python

# Default target
.PHONY: help
help:
	@echo "Available targets:"
	@echo "  install    - Create virtual environment and install dependencies"
	@echo "  run        - Run the 3D voxel world application"
	@echo "  debug      - Run with additional debug output"
	@echo "  profile    - Run with performance profiling"
	@echo "  quick      - Quick launch with minimal pre-generation"
	@echo "  test       - Run simple OpenGL test"
	@echo "  clean      - Remove virtual environment and cache files"
	@echo "  check      - Check virtual environment status"
	@echo "  help       - Show this help message"

# Create virtual environment and install dependencies
.PHONY: install
install: $(VENV_DIR)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "Virtual environment created and dependencies installed!"
	@echo "Run 'make run' to start the application."

# Create virtual environment
$(VENV_DIR):
	$(PYTHON) -m venv $(VENV_DIR)

# Run the application
.PHONY: run
run: $(VENV_DIR)
	@if [ ! -f $(PYTHON_VENV) ]; then \
		echo "Virtual environment not found. Run 'make install' first."; \
		exit 1; \
	fi
	DRI_PRIME=1 PYOPENGL_PLATFORM=glx $(PYTHON_VENV) main.py

# Run with debug output
.PHONY: debug
debug: $(VENV_DIR)
	@if [ ! -f $(PYTHON_VENV) ]; then \
		echo "Virtual environment not found. Run 'make install' first."; \
		exit 1; \
	fi
	@echo "Running with debug environment variables:"
	@echo "DRI_PRIME=1 PYOPENGL_PLATFORM=glx"
	DRI_PRIME=1 PYOPENGL_PLATFORM=glx $(PYTHON_VENV) -v main.py

# Run with performance profiling
.PHONY: profile
profile: $(VENV_DIR)
	@if [ ! -f $(PYTHON_VENV) ]; then \
		echo "Virtual environment not found. Run 'make install' first."; \
		exit 1; \
	fi
	@echo "Running with performance profiling..."
	@echo "DRI_PRIME=1 PYOPENGL_PLATFORM=glx"
	DRI_PRIME=1 PYOPENGL_PLATFORM=glx $(PYTHON_VENV) -m cProfile -s cumulative main.py

# Quick launch with minimal setup for testing
.PHONY: quick
quick: $(VENV_DIR)
	@if [ ! -f $(PYTHON_VENV) ]; then \
		echo "Virtual environment not found. Run 'make install' first."; \
		exit 1; \
	fi
	@echo "Quick launch with reduced pre-generation..."
	@echo "DRI_PRIME=1 PYOPENGL_PLATFORM=glx"
	QUICK_MODE=1 DRI_PRIME=1 PYOPENGL_PLATFORM=glx $(PYTHON_VENV) main.py

# Test OpenGL functionality
.PHONY: test
test: $(VENV_DIR)
	@if [ ! -f $(PYTHON_VENV) ]; then \
		echo "Virtual environment not found. Run 'make install' first."; \
		exit 1; \
	fi
	@echo "Testing OpenGL setup..."
	DRI_PRIME=1 PYOPENGL_PLATFORM=glx $(PYTHON_VENV) test_opengl.py

# Clean up virtual environment and cache files
.PHONY: clean
clean:
	@echo "Removing virtual environment and cache files..."
	rm -rf $(VENV_DIR)
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "Cleanup complete!"

# Development target to check if environment is set up
.PHONY: check
check:
	@if [ -d $(VENV_DIR) ]; then \
		echo "Virtual environment exists at $(VENV_DIR)"; \
		echo "Python version: $$($(PYTHON_VENV) --version)"; \
		echo "Installed packages:"; \
		$(PIP) list; \
	else \
		echo "Virtual environment not found. Run 'make install' to create it."; \
	fi

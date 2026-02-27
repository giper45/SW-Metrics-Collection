# docs/Makefile
# Recursively compiles all .puml files into PNG images.
# Output directory: docs/rendered/png/**/<file>.png
# Folder structure is preserved.

SHELL := /bin/bash

# Root directory (this Makefile lives inside docs/)
DOCS_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
OUT_DIR  := $(DOCS_DIR)/rendered/png

# PlantUML command:
# If installed locally: plantuml
# Or use: java -jar /path/to/plantuml.jar
PLANTUML ?= plantuml

# Default options:
# -tpng: generate PNG
# -charset utf-8: avoid encoding issues
PLANTUML_OPTS ?= -charset utf-8 -tpng

# Find all .puml files recursively (excluding rendered directory)
PUML_SOURCES := $(shell find "$(DOCS_DIR)" -type f -name '*.puml' \
	-not -path "$(OUT_DIR)/*" -not -path "$(DOCS_DIR)/rendered/*" | sort)

# Map .puml files to corresponding PNG output files
# docs/section/a.puml -> docs/rendered/png/section/a.png
PNGS := $(patsubst $(DOCS_DIR)/%.puml,$(OUT_DIR)/%.png,$(PUML_SOURCES))

.PHONY: all png clean list check help

all: png

help:
	@echo "Targets:"
	@echo "  make png    - compile all .puml files into PNG (recursive)"
	@echo "  make list   - list all detected .puml files"
	@echo "  make clean  - remove docs/rendered/png directory"
	@echo ""
	@echo "Variables:"
	@echo "  PLANTUML=<command>       (default: plantuml)"
	@echo "  PLANTUML_OPTS=<options>  (default: -charset utf-8 -tpng)"
	@echo ""
	@echo "Examples:"
	@echo "  make png"
	@echo "  make png PLANTUML='java -jar ../tools/plantuml.jar'"
	@echo "  make clean"

check:
	@echo "Using PLANTUML=$(PLANTUML)"
	@command -v $(word 1,$(PLANTUML)) >/dev/null 2>&1 || \
	echo "PlantUML not found in PATH. You may need to specify PLANTUML='java -jar path/to/plantuml.jar'"

list:
	@echo "Found $(words $(PUML_SOURCES)) .puml files:"
	@printf "%s\n" $(PUML_SOURCES)

png: $(PNGS)
	@echo "Generated $(words $(PNGS)) PNG files in: $(OUT_DIR)"

# Rule to compile each .puml file
$(OUT_DIR)/%.png: $(DOCS_DIR)/%.puml
	@mkdir -p "$(dir $@)"
	@echo "Compiling: $< -> $@"
	@$(PLANTUML) $(PLANTUML_OPTS) -o "$(dir $@)" "$<" >/dev/null

clean:
	@rm -rf "$(OUT_DIR)"
	@echo "🧹 Cleaned: $(OUT_DIR)"
SRC_DIR := $(PWD)/src
RESULTS_DIR := $(PWD)/results
RESULTS_NORMALIZED_DIR := $(PWD)/results_normalized
ANALYSIS_OUT_DIR := $(PWD)/analysis_out
JAVA_BUILDER_DIR := $(PWD)/metrics/java-builder
METRIC_CONTAINER_UID ?= $(shell id -u)
METRIC_CONTAINER_GID ?= $(shell id -g)
METRIC_CONTAINER_HOME ?= /tmp
CASE_STUDY_RUN_ID := $(if $(METRIC_RUN_ID),$(METRIC_RUN_ID),$(shell python3 -c 'import uuid; print(uuid.uuid4())'))
EXPERIMENT_RUN_ID := $(CASE_STUDY_RUN_ID)
METRIC_RESOURCE_TRACKING ?= 0
METRIC_RESOURCE_SAMPLE_SEC ?= 0.5
METRIC_RESOURCE_REPORT ?= $(ANALYSIS_OUT_DIR)/metric-runtime-$(CASE_STUDY_RUN_ID).jsonl
JAVA_BUILD_BYTECODE ?= 1
JAVA_BUILD_STRICT ?= 0
JAVA_BUILD_FORCE ?= 0
DOCKER_RUN_USER_FLAGS := --user $(METRIC_CONTAINER_UID):$(METRIC_CONTAINER_GID) -e HOME=$(METRIC_CONTAINER_HOME)
DOCKER_RUN_METRIC_BASE := docker run --rm $(DOCKER_RUN_USER_FLAGS) -e METRIC_RUN_ID=$(CASE_STUDY_RUN_ID) -v $(SRC_DIR):/app:ro -v $(RESULTS_DIR):/results
DOCKER_RUN_METRIC := python3 -m analysis.metric_runtime_monitor --run-id $(CASE_STUDY_RUN_ID) --results-dir $(RESULTS_DIR) --enabled $(METRIC_RESOURCE_TRACKING) --sample-interval-sec $(METRIC_RESOURCE_SAMPLE_SEC) --out $(METRIC_RESOURCE_REPORT) -- $(DOCKER_RUN_METRIC_BASE)
DOCKER_BUILD_METRIC := DOCKER_BUILDKIT=1 docker build --build-context repo_common=$(PWD)/metrics/common
DOCKER_RUN_METRIC_AMD64_BASE := docker run --platform=linux/amd64 --rm $(DOCKER_RUN_USER_FLAGS) -e METRIC_RUN_ID=$(CASE_STUDY_RUN_ID) -v $(SRC_DIR):/app:ro -v $(RESULTS_DIR):/results
DOCKER_RUN_METRIC_AMD64 := python3 -m analysis.metric_runtime_monitor --run-id $(CASE_STUDY_RUN_ID) --results-dir $(RESULTS_DIR) --enabled $(METRIC_RESOURCE_TRACKING) --sample-interval-sec $(METRIC_RESOURCE_SAMPLE_SEC) --out $(METRIC_RESOURCE_REPORT) -- $(DOCKER_RUN_METRIC_AMD64_BASE)
DOCKER_BUILD_METRIC_AMD64 := DOCKER_BUILDKIT=1 docker build --platform=linux/amd64 --build-context repo_common=$(PWD)/metrics/common
CODEQL_DOCKER_ENV := \
	$(if $(CODEQL_THREADS),-e CODEQL_THREADS=$(CODEQL_THREADS),) \
	$(if $(CODEQL_RAM_MB),-e CODEQL_RAM_MB=$(CODEQL_RAM_MB),) \
	$(if $(CODEQL_JAVA_QUERY_SUITE),-e CODEQL_JAVA_QUERY_SUITE=$(CODEQL_JAVA_QUERY_SUITE),) \
	$(if $(CODEQL_JAVA_BUILD_MODE),-e CODEQL_JAVA_BUILD_MODE=$(CODEQL_JAVA_BUILD_MODE),) \
	$(if $(CODEQL_JAVA_BUILD_COMMAND),-e CODEQL_JAVA_BUILD_COMMAND=$(CODEQL_JAVA_BUILD_COMMAND),) \
	$(if $(CODEQL_JAVA_EXTRACTOR_OPTIONS),-e CODEQL_JAVA_EXTRACTOR_OPTIONS=$(CODEQL_JAVA_EXTRACTOR_OPTIONS),) \
	$(if $(CODEQL_JAVA_USE_PREPARED_BYTECODE),-e CODEQL_JAVA_USE_PREPARED_BYTECODE=$(CODEQL_JAVA_USE_PREPARED_BYTECODE),) \
	$(if $(CODEQL_DATABASE_CREATE_ARGS),-e CODEQL_DATABASE_CREATE_ARGS=$(CODEQL_DATABASE_CREATE_ARGS),) \
	$(if $(CODEQL_DATABASE_ANALYZE_ARGS),-e CODEQL_DATABASE_ANALYZE_ARGS=$(CODEQL_DATABASE_ANALYZE_ARGS),) \
	$(if $(CODEQL_EXTRACTOR_JAVA_JSP),-e CODEQL_EXTRACTOR_JAVA_JSP=$(CODEQL_EXTRACTOR_JAVA_JSP),)

.PHONY: \
	collect-loc-cloc \
	collect-loc-tokei \
	collect-loc-scc \
	collect-class-count-javaparser \
	collect-package-count-javaparser \
	collect-normalized-loc-cloc \
	collect-cc-lizard \
	collect-cc-radon \
	collect-cc-ck \
	collect-ce-ca-jdepend \
	collect-ce-ca-ck-cbo \
	collect-lcom-ck \
	collect-lcom-ckjm \
	collect-duplication-jscpd \
	collect-mi-halstead-java \
	collect-coverage-jacoco \
	collect-vulnerability-dependency-check \
	collect-vulnerability-codeql-java \
	collect-vulnerability-pmd-security \
	collect-vulnerability-pmd-jsp-security \
	collect-vulnerability-spotbugs-findsecbugs \
	collect-churn-git \
	collect-size-all \
	collect-complexity-all \
	collect-coupling-all \
	collect-cohesion-all \
	collect-vulnerability-all \
	collect-paper-extras \
	collect-all \
	prepare-java-bytecode \
	prepare-java-bytecode-if-enabled \
	repair-output-permissions \
	clean-case-study \
	print-case-study \
	case-study \
	case-studies \
	clean-experiment \
	print-experiment \
	print-run-id \
	manifest \
	normalize \
	dataset \
	agreement \
	report \
	compute-structure-inventory \
	experiment \
	experiments \
	paper-tables \
	validate-results \
	normalize-vulnerability-sarif \
	test-unit \
	test-docker-matrix

collect-loc-cloc:
	@# Build the LOC collector image backed by cloc.
	$(DOCKER_BUILD_METRIC) -t loc-cloc:latest metrics/size/generic/loc-cloc
	@# Run the cloc collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) loc-cloc:latest

collect-loc-tokei:
	@# Build the LOC collector image backed by tokei.
	$(DOCKER_BUILD_METRIC) -t loc-tokei:latest metrics/size/generic/loc-tokei
	@# Run the tokei collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) loc-tokei:latest

collect-loc-scc:
	@# Build the LOC collector image backed by scc.
	$(DOCKER_BUILD_METRIC) -t loc-scc:latest metrics/size/generic/loc-scc
	@# Run the scc collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) loc-scc:latest

collect-class-count-javaparser:
	@# Build the JavaParser-based class counting image.
	$(DOCKER_BUILD_METRIC) -t class-count-javaparser:latest metrics/size/java/class-count-javaparser
	@# Run the class counting collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) class-count-javaparser:latest

collect-package-count-javaparser:
	@# Build the JavaParser-based package counting image.
	$(DOCKER_BUILD_METRIC) -t package-count-javaparser:latest metrics/size/java/package-count-javaparser
	@# Run the package counting collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) package-count-javaparser:latest

collect-normalized-loc-cloc:
	@# Build the generic normalized collector image.
	$(DOCKER_BUILD_METRIC) -t normalized-collector:latest metrics/generic/normalized-collector
	@# Run the normalized collector with LOC/cloc-specific environment overrides.
	$(DOCKER_RUN_METRIC) \
		-e METRIC_KEY=loc \
		-e TOOL_KEY=cloc \
		-e COMMAND='cloc --json --quiet --skip-uniqueness {project_path}' \
		-e TOOL_VERSION_COMMAND='cloc --version' \
		-e ENTITY_TYPE=project \
		-e VARIANT_KEY=default \
		-e SCOPE_FILTER=no_tests \
		normalized-collector:latest

collect-cc-lizard:
	@# Build the Lizard-based complexity collector image.
	$(DOCKER_BUILD_METRIC) -t cc-lizard:latest metrics/complexity/generic/cc-lizard
	@# Run the Lizard collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) cc-lizard:latest

collect-cc-radon:
	@# Build the Radon-based Python complexity collector image.
	$(DOCKER_BUILD_METRIC) -t cc-radon:latest metrics/complexity/python/cc-radon
	@# Run the Radon collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) cc-radon:latest

collect-cc-ck:
	@# Build the CK-based Java complexity collector image.
	$(DOCKER_BUILD_METRIC) -t cc-ck:latest metrics/complexity/java/cc-ck
	@# Run the CK collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) cc-ck:latest

collect-ce-ca-jdepend:
	@# Build the JDepend-based coupling collector image.
	$(DOCKER_BUILD_METRIC) -t ce-ca-jdepend:latest metrics/coupling/java/ce-ca-jdepend
	@# Run the JDepend collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) ce-ca-jdepend:latest

collect-ce-ca-ck-cbo:
	@# Build the CK/CBO-based coupling collector image.
	$(DOCKER_BUILD_METRIC) -t ce-ca-ck-cbo:latest metrics/coupling/java/ce-ca-ck-cbo
	@# Run the CK/CBO collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) ce-ca-ck-cbo:latest

collect-lcom-ck:
	@# Build the CK-based cohesion collector image.
	$(DOCKER_BUILD_METRIC) -t lcom-ck:latest metrics/cohesion/java/lcom-ck
	@# Run the CK cohesion collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) lcom-ck:latest

collect-lcom-ckjm:
	@# Build the CKJM-based cohesion collector image.
	$(DOCKER_BUILD_METRIC) -t lcom-ckjm:latest metrics/cohesion/java/lcom-ckjm
	@# Run the CKJM cohesion collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) lcom-ckjm:latest

collect-duplication-jscpd:
	@# Build the JSCPD-based duplication collector image.
	$(DOCKER_BUILD_METRIC) -t duplication-jscpd:latest metrics/duplication/java/duplication-jscpd
	@# Run the JSCPD collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) duplication-jscpd:latest

collect-mi-halstead-java:
	@# Build the Halstead/MI collector image.
	$(DOCKER_BUILD_METRIC) -t mi-halstead-java:latest metrics/maintainability/java/mi-halstead-java
	@# Run the Halstead/MI collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) mi-halstead-java:latest

collect-coverage-jacoco:
	@# Build the JaCoCo coverage collector image.
	$(DOCKER_BUILD_METRIC) -t coverage-jacoco:latest metrics/testing/java/coverage-jacoco
	@# Run the JaCoCo coverage collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) coverage-jacoco:latest

collect-vulnerability-dependency-check:
	@# Build the OWASP Dependency-Check collector image.
	$(DOCKER_BUILD_METRIC) -t vulnerability-dependency-check:latest metrics/vulnerability/java/vulnerability-dependency-check
	@# Run the Dependency-Check collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) vulnerability-dependency-check:latest

collect-vulnerability-codeql-java:
	@# Build the CodeQL collector image for linux/amd64.
	$(DOCKER_BUILD_METRIC_AMD64) -t vulnerability-codeql-java:latest metrics/vulnerability/java/vulnerability-codeql-java
	@# Run the CodeQL collector on an amd64 container against the repositories in src/.
	$(DOCKER_RUN_METRIC_AMD64) $(CODEQL_DOCKER_ENV) vulnerability-codeql-java:latest

collect-vulnerability-pmd-security:
	@# Build the PMD security collector image.
	$(DOCKER_BUILD_METRIC) -t vulnerability-pmd-security:latest metrics/vulnerability/java/vulnerability-pmd-security
	@# Run the PMD security collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) vulnerability-pmd-security:latest

collect-vulnerability-pmd-jsp-security:
	@# Build the PMD JSP security collector image.
	$(DOCKER_BUILD_METRIC) -t vulnerability-pmd-jsp-security:latest metrics/vulnerability/web/vulnerability-pmd-jsp-security
	@# Run the PMD JSP security collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) vulnerability-pmd-jsp-security:latest

collect-vulnerability-spotbugs-findsecbugs:
	@# Build the SpotBugs/FindSecBugs collector image.
	$(DOCKER_BUILD_METRIC) -t vulnerability-spotbugs-findsecbugs:latest metrics/vulnerability/java/vulnerability-spotbugs-findsecbugs
	@# Run the SpotBugs/FindSecBugs collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) vulnerability-spotbugs-findsecbugs:latest

collect-churn-git:
	@# Build the Git churn collector image.
	$(DOCKER_BUILD_METRIC) -t churn-git:latest metrics/evolution/generic/churn-git
	@# Run the Git churn collector against the repositories mounted under src/.
	$(DOCKER_RUN_METRIC) churn-git:latest

collect-size-all: collect-loc-cloc collect-loc-tokei collect-loc-scc collect-class-count-javaparser collect-package-count-javaparser
collect-complexity-all: collect-cc-lizard collect-cc-ck
collect-coupling-all: collect-ce-ca-jdepend collect-ce-ca-ck-cbo
collect-cohesion-all: collect-lcom-ck collect-lcom-ckjm
collect-vulnerability-all: collect-vulnerability-dependency-check collect-vulnerability-codeql-java collect-vulnerability-pmd-security collect-vulnerability-pmd-jsp-security collect-vulnerability-spotbugs-findsecbugs
collect-paper-extras: collect-duplication-jscpd collect-mi-halstead-java collect-coverage-jacoco

prepare-java-bytecode:
	@# Compile Java repositories into bytecode before bytecode-based metrics run.
	python3 -m analysis.prepare_java_bytecode --src-dir $(SRC_DIR) --builder-dir $(JAVA_BUILDER_DIR) $(if $(filter 1,$(JAVA_BUILD_STRICT)),--strict,) $(if $(filter 1,$(JAVA_BUILD_FORCE)),--force,)

prepare-java-bytecode-if-enabled:
	@# Run bytecode preparation only when JAVA_BUILD_BYTECODE=1 is enabled.
	@if [ "$(JAVA_BUILD_BYTECODE)" = "1" ]; then \
		$(MAKE) prepare-java-bytecode JAVA_BUILD_STRICT=$(JAVA_BUILD_STRICT) JAVA_BUILD_FORCE=$(JAVA_BUILD_FORCE); \
	else \
		echo "Skipping Java bytecode build (set JAVA_BUILD_BYTECODE=1 to enable)"; \
	fi

repair-output-permissions:
	@# Reassign output ownership to the current host user after older root-owned container runs.
	docker run --rm -v $(PWD):/workspace alpine:3.22 sh -lc 'mkdir -p /workspace/results /workspace/results_normalized /workspace/analysis_out && chown -R $(METRIC_CONTAINER_UID):$(METRIC_CONTAINER_GID) /workspace/results /workspace/results_normalized /workspace/analysis_out'

clean-experiment:
	@# Remove previous raw, normalized, and analysis outputs.
	rm -rf $(RESULTS_DIR) $(RESULTS_NORMALIZED_DIR) $(ANALYSIS_OUT_DIR)
	@# Recreate the output directories expected by the pipeline.
	mkdir -p $(RESULTS_DIR) $(RESULTS_NORMALIZED_DIR) $(ANALYSIS_OUT_DIR)

clean-src:
	@# Remove all repositories currently staged under src/.
	rm -rf $(SRC_DIR)/*

print-experiment:
	@# Print the table header for the collector catalog.
	@printf "%-35s %-55s %s\n" "DOCKER_IMAGE" "PATH" "METRIC_TYPE"
	@# Print a visual separator under the header row.
	@printf "%-35s %-55s %s\n" "-----------------------------------" "-------------------------------------------------------" "---------------------------"
	@# Print one row per collector image and its metric family.
	@printf "%-35s %-55s %s\n" "loc-cloc:latest" "metrics/size/generic/loc-cloc" "loc"
	@printf "%-35s %-55s %s\n" "loc-tokei:latest" "metrics/size/generic/loc-tokei" "loc"
	@printf "%-35s %-55s %s\n" "loc-scc:latest" "metrics/size/generic/loc-scc" "loc"
	@printf "%-35s %-55s %s\n" "class-count-javaparser:latest" "metrics/size/java/class-count-javaparser" "class-count"
	@printf "%-35s %-55s %s\n" "package-count-javaparser:latest" "metrics/size/java/package-count-javaparser" "package-count"
	@printf "%-35s %-55s %s\n" "cc-lizard:latest" "metrics/complexity/generic/cc-lizard" "cc"
	@printf "%-35s %-55s %s\n" "cc-ck:latest" "metrics/complexity/java/cc-ck" "wmc, nom"
	@printf "%-35s %-55s %s\n" "ce-ca-jdepend:latest" "metrics/coupling/java/ce-ca-jdepend" "ce-ca"
	@printf "%-35s %-55s %s\n" "ce-ca-ck-cbo:latest" "metrics/coupling/java/ce-ca-ck-cbo" "ce-ca"
	@printf "%-35s %-55s %s\n" "lcom-ck:latest" "metrics/cohesion/java/lcom-ck" "lcom"
	@printf "%-35s %-55s %s\n" "lcom-ckjm:latest" "metrics/cohesion/java/lcom-ckjm" "lcom"
	@printf "%-35s %-55s %s\n" "duplication-jscpd:latest" "metrics/duplication/java/duplication-jscpd" "duplication-rate"
	@printf "%-35s %-55s %s\n" "mi-halstead-java:latest" "metrics/maintainability/java/mi-halstead-java" "maintainability-index"
	@printf "%-35s %-55s %s\n" "coverage-jacoco:latest" "metrics/testing/java/coverage-jacoco" "test-coverage"
	@printf "%-35s %-55s %s\n" "vulnerability-dependency-check:latest" "metrics/vulnerability/java/vulnerability-dependency-check" "vulnerability-findings"
	@printf "%-35s %-55s %s\n" "vulnerability-codeql-java:latest" "metrics/vulnerability/java/vulnerability-codeql-java" "vulnerability-findings"
	@printf "%-35s %-55s %s\n" "vulnerability-pmd-security:latest" "metrics/vulnerability/java/vulnerability-pmd-security" "vulnerability-findings"
	@printf "%-35s %-55s %s\n" "vulnerability-pmd-jsp-security:latest" "metrics/vulnerability/web/vulnerability-pmd-jsp-security" "vulnerability-findings"
	@printf "%-35s %-55s %s\n" "vulnerability-spotbugs-findsecbugs:latest" "metrics/vulnerability/java/vulnerability-spotbugs-findsecbugs" "vulnerability-findings"

print-run-id:
	@# Print the run identifier that will be attached to metric results.
	@echo "Using METRIC_RUN_ID=$(CASE_STUDY_RUN_ID)"
	@# Print whether runtime telemetry is enabled and where it will be written.
	@echo "Metric resource tracking=$(METRIC_RESOURCE_TRACKING) report=$(METRIC_RESOURCE_REPORT)"

collect-all: print-run-id prepare-java-bytecode-if-enabled collect-size-all collect-complexity-all collect-coupling-all collect-cohesion-all collect-vulnerability-all collect-paper-extras

manifest:
	@# Build the manifest describing the expected metric outputs for this run.
	python3 -m analysis.build_manifest \
		--results-dir $(RESULTS_DIR) \
		--run-id $(CASE_STUDY_RUN_ID) \
		--out $(RESULTS_DIR)/manifest-$(CASE_STUDY_RUN_ID).json \
		--primary-component-type file \
		--language java \
		--expected 'loc:cloc:cloc-default,loc:tokei:tokei-default,loc:scc:scc-default,class-count:javaparser:javaparser-default,package-count:javaparser:javaparser-default,cc:lizard:lizard-default,wmc:ck:ck-raw,nom:ck:ck-raw,ce-ca:jdepend:jdepend-default,ce-ca:ck:ck-ce-ca-proxy,lcom:ck:ck-default,lcom:ckjm:ckjm-default,vulnerability-findings:dependency-check:dependency-check-default,vulnerability-findings:codeql:codeql-java-security-extended,vulnerability-findings:pmd:pmd-java-security,vulnerability-findings:pmd:pmd-jsp-security,vulnerability-findings:spotbugs:spotbugs-findsecbugs-default,duplication-rate:jscpd:jscpd-default,maintainability-index:java-halstead-analyzer:mi-halstead-default,test-coverage:jacoco:jacoco-default'

normalize:
	@# Normalize raw metric outputs into the shared JSONL schema.
	python3 -m analysis.normalize $(RESULTS_DIR) $(RESULTS_NORMALIZED_DIR)

normalize-vulnerability-sarif:
	@# Normalize SARIF vulnerability outputs into the shared schema.
	python3 -m analysis.normalize_vulnerability_sarif --results-dir $(RESULTS_DIR)

dataset:
	@# Build analysis datasets from normalized metric outputs.
	python3 -m analysis.build_dataset --in $(RESULTS_NORMALIZED_DIR) --out $(ANALYSIS_OUT_DIR) --wide-component-type file

agreement:
	@# Compute inter-tool agreement over the long-form dataset.
	python3 -m analysis.agreement --in $(ANALYSIS_OUT_DIR)/dataset_long.csv --out $(ANALYSIS_OUT_DIR)/agreement.csv

report:
	@# Generate repository-level summary reports in CSV and JSON form.
	python3 -m analysis.report_repository --normalized $(RESULTS_NORMALIZED_DIR) --long $(ANALYSIS_OUT_DIR)/dataset_long.csv --out $(ANALYSIS_OUT_DIR)/repo_report.csv --out-json $(ANALYSIS_OUT_DIR)/repo_report.json

compute-structure-inventory:
	@# Aggregate repository structure metrics such as classes and packages.
	python3 -m analysis.structure_inventory --results-dir $(RESULTS_DIR) --out-csv $(ANALYSIS_OUT_DIR)/structure_inventory.csv --out-json $(ANALYSIS_OUT_DIR)/structure_inventory.json

clean-case-study: clean-experiment

print-case-study: print-experiment

case-study: clean-case-study collect-all manifest normalize dataset agreement report

case-studies: case-study

experiment: case-study

experiments: case-studies

paper-tables:
	@# Render publication-ready agreement tables from the analysis outputs.
	python3 -m analysis.paper_tables \
		--agreement $(ANALYSIS_OUT_DIR)/agreement.csv \
		--out-dir $(ANALYSIS_OUT_DIR) \
		--tex-dir $(ANALYSIS_OUT_DIR) \
		--min-common 2

validate-results:
	@# Build the JSONL schema validator image.
	$(DOCKER_BUILD_METRIC) -t jsonl-schema-validator:latest metrics/validate-results/generic/jsonl-schema-validator
	@# Validate the collected result files against the schema.
	docker run --rm -v $(RESULTS_DIR):/results jsonl-schema-validator:latest

test-unit:
	@# Run the Python unit test suite.
	python3 -m pytest tests/unit -q

test-docker-matrix:
	@# Run the integration matrix that exercises metric Docker images.
	python3 tests/integration/run_docker_matrix_tests.py


clean:
	@# Remove files produced in the results and analysis directories.
	rm -rf $(RESULTS_DIR)/* $(RESULTS_NORMALIZED_DIR)/* $(ANALYSIS_OUT_DIR)/*


archive:
	@# Export the current Git HEAD as a zip archive.
	git archive -o sw-metrics-collection-$(shell git rev-parse --short HEAD).zip HEAD

SRC_DIR := $(PWD)/src
RESULTS_DIR := $(PWD)/results
RESULTS_NORMALIZED_DIR := $(PWD)/results_normalized
ANALYSIS_OUT_DIR := $(PWD)/analysis_out
JAVA_BUILDER_DIR := $(PWD)/metrics/java-builder
EXPERIMENT_RUN_ID := $(if $(METRIC_RUN_ID),$(METRIC_RUN_ID),$(shell python3 -c 'import uuid; print(uuid.uuid4())'))
METRIC_RESOURCE_TRACKING ?= 0
METRIC_RESOURCE_SAMPLE_SEC ?= 0.5
METRIC_RESOURCE_REPORT ?= $(ANALYSIS_OUT_DIR)/metric-runtime-$(EXPERIMENT_RUN_ID).jsonl
JAVA_BUILD_BYTECODE ?= 0
JAVA_BUILD_STRICT ?= 0
JAVA_BUILD_FORCE ?= 0
DOCKER_RUN_METRIC_BASE := docker run --rm -e METRIC_RUN_ID=$(EXPERIMENT_RUN_ID) -v $(SRC_DIR):/app:ro -v $(RESULTS_DIR):/results
DOCKER_RUN_METRIC := python3 -m analysis.metric_runtime_monitor --run-id $(EXPERIMENT_RUN_ID) --results-dir $(RESULTS_DIR) --enabled $(METRIC_RESOURCE_TRACKING) --sample-interval-sec $(METRIC_RESOURCE_SAMPLE_SEC) --out $(METRIC_RESOURCE_REPORT) -- $(DOCKER_RUN_METRIC_BASE)
DOCKER_BUILD_METRIC := DOCKER_BUILDKIT=1 docker build --build-context repo_common=$(PWD)/metrics/common

.PHONY: \
	collect-loc-cloc \
	collect-loc-tokei \
	collect-loc-scc \
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
	collect-static-warnings-checkstyle \
	collect-coverage-jacoco \
	collect-churn-git \
	collect-size-all \
	collect-complexity-all \
	collect-coupling-all \
	collect-cohesion-all \
	collect-paper-extras \
	collect-all \
	prepare-java-bytecode \
	prepare-java-bytecode-if-enabled \
	clean-experiment \
	print-run-id \
	manifest \
	normalize \
	dataset \
	agreement \
	report \
	experiment \
	experiments \
	paper-tables \
	validate-results \
	test-unit \
	test-docker-matrix

collect-loc-cloc:
	$(DOCKER_BUILD_METRIC) -t loc-cloc:latest metrics/size/generic/loc-cloc
	$(DOCKER_RUN_METRIC) loc-cloc:latest

collect-loc-tokei:
	$(DOCKER_BUILD_METRIC) -t loc-tokei:latest metrics/size/generic/loc-tokei
	$(DOCKER_RUN_METRIC) loc-tokei:latest

collect-loc-scc:
	$(DOCKER_BUILD_METRIC) -t loc-scc:latest metrics/size/generic/loc-scc
	$(DOCKER_RUN_METRIC) loc-scc:latest

collect-normalized-loc-cloc:
	$(DOCKER_BUILD_METRIC) -t normalized-collector:latest metrics/generic/normalized-collector
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
	$(DOCKER_BUILD_METRIC) -t cc-lizard:latest metrics/complexity/generic/cc-lizard
	$(DOCKER_RUN_METRIC) cc-lizard:latest

collect-cc-radon:
	$(DOCKER_BUILD_METRIC) -t cc-radon:latest metrics/complexity/python/cc-radon
	$(DOCKER_RUN_METRIC) cc-radon:latest

collect-cc-ck:
	$(DOCKER_BUILD_METRIC) -t cc-ck:latest metrics/complexity/java/cc-ck
	$(DOCKER_RUN_METRIC) cc-ck:latest

collect-ce-ca-jdepend:
	$(DOCKER_BUILD_METRIC) -t ce-ca-jdepend:latest metrics/coupling/java/ce-ca-jdepend
	$(DOCKER_RUN_METRIC) ce-ca-jdepend:latest

collect-ce-ca-ck-cbo:
	$(DOCKER_BUILD_METRIC) -t ce-ca-ck-cbo:latest metrics/coupling/java/ce-ca-ck-cbo
	$(DOCKER_RUN_METRIC) ce-ca-ck-cbo:latest

collect-lcom-ck:
	$(DOCKER_BUILD_METRIC) -t lcom-ck:latest metrics/cohesion/java/lcom-ck
	$(DOCKER_RUN_METRIC) lcom-ck:latest

collect-lcom-ckjm:
	$(DOCKER_BUILD_METRIC) -t lcom-ckjm:latest metrics/cohesion/java/lcom-ckjm
	$(DOCKER_RUN_METRIC) lcom-ckjm:latest

collect-duplication-jscpd:
	$(DOCKER_BUILD_METRIC) -t duplication-jscpd:latest metrics/duplication/java/duplication-jscpd
	$(DOCKER_RUN_METRIC) duplication-jscpd:latest

collect-mi-halstead-java:
	$(DOCKER_BUILD_METRIC) -t mi-halstead-java:latest metrics/maintainability/java/mi-halstead-java
	$(DOCKER_RUN_METRIC) mi-halstead-java:latest

collect-static-warnings-checkstyle:
	$(DOCKER_BUILD_METRIC) -t static-warnings-checkstyle:latest metrics/quality/java/static-warnings-checkstyle
	$(DOCKER_RUN_METRIC) static-warnings-checkstyle:latest

collect-coverage-jacoco:
	$(DOCKER_BUILD_METRIC) -t coverage-jacoco:latest metrics/testing/java/coverage-jacoco
	$(DOCKER_RUN_METRIC) coverage-jacoco:latest

collect-churn-git:
	$(DOCKER_BUILD_METRIC) -t churn-git:latest metrics/evolution/generic/churn-git
	$(DOCKER_RUN_METRIC) churn-git:latest

collect-size-all: collect-loc-cloc collect-loc-tokei collect-loc-scc
collect-complexity-all: collect-cc-lizard collect-cc-ck
collect-coupling-all: collect-ce-ca-jdepend collect-ce-ca-ck-cbo
collect-cohesion-all: collect-lcom-ck collect-lcom-ckjm
collect-paper-extras: collect-duplication-jscpd collect-mi-halstead-java collect-static-warnings-checkstyle collect-coverage-jacoco collect-churn-git

prepare-java-bytecode:
	python3 -m analysis.prepare_java_bytecode --src-dir $(SRC_DIR) --builder-dir $(JAVA_BUILDER_DIR) $(if $(filter 1,$(JAVA_BUILD_STRICT)),--strict,) $(if $(filter 1,$(JAVA_BUILD_FORCE)),--force,)

prepare-java-bytecode-if-enabled:
	@if [ "$(JAVA_BUILD_BYTECODE)" = "1" ]; then \
		$(MAKE) prepare-java-bytecode JAVA_BUILD_STRICT=$(JAVA_BUILD_STRICT) JAVA_BUILD_FORCE=$(JAVA_BUILD_FORCE); \
	else \
		echo "Skipping Java bytecode build (set JAVA_BUILD_BYTECODE=1 to enable)"; \
	fi

clean-experiment:
	rm -rf $(RESULTS_DIR) $(RESULTS_NORMALIZED_DIR) $(ANALYSIS_OUT_DIR)
	mkdir -p $(RESULTS_DIR) $(RESULTS_NORMALIZED_DIR) $(ANALYSIS_OUT_DIR)

print-run-id:
	@echo "Using METRIC_RUN_ID=$(EXPERIMENT_RUN_ID)"
	@echo "Metric resource tracking=$(METRIC_RESOURCE_TRACKING) report=$(METRIC_RESOURCE_REPORT)"

collect-all: print-run-id prepare-java-bytecode-if-enabled collect-size-all collect-complexity-all collect-coupling-all collect-cohesion-all collect-paper-extras

manifest:
	python3 -m analysis.build_manifest \
		--results-dir $(RESULTS_DIR) \
		--run-id $(EXPERIMENT_RUN_ID) \
		--out $(RESULTS_DIR)/manifest-$(EXPERIMENT_RUN_ID).json \
		--primary-component-type file \
		--language java \
		--expected 'loc:cloc:cloc-default,loc:tokei:tokei-default,loc:scc:scc-default,cc:lizard:lizard-default,wmc:ck:ck-raw,nom:ck:ck-raw,ce-ca:jdepend:jdepend-default,ce-ca:ck:ck-ce-ca-proxy,lcom:ck:ck-default,lcom:ckjm:ckjm-default,duplication-rate:jscpd:jscpd-default,maintainability-index:java-halstead-analyzer:mi-halstead-default,static-warnings:checkstyle:checkstyle-default,test-coverage:jacoco:jacoco-default,code-churn:git:git-default'

normalize:
	python3 -m analysis.normalize $(RESULTS_DIR) $(RESULTS_NORMALIZED_DIR)

dataset:
	python3 -m analysis.build_dataset --in $(RESULTS_NORMALIZED_DIR) --out $(ANALYSIS_OUT_DIR) --wide-component-type file

agreement:
	python3 -m analysis.agreement --in $(ANALYSIS_OUT_DIR)/dataset_long.csv --out $(ANALYSIS_OUT_DIR)/agreement.csv

report:
	python3 -m analysis.report_repository --normalized $(RESULTS_NORMALIZED_DIR) --long $(ANALYSIS_OUT_DIR)/dataset_long.csv --out $(ANALYSIS_OUT_DIR)/repo_report.csv --out-json $(ANALYSIS_OUT_DIR)/repo_report.json

experiment: clean-experiment collect-all manifest normalize dataset agreement report

experiments: experiment

paper-tables:
	python3 -m analysis.paper_tables \
		--agreement $(ANALYSIS_OUT_DIR)/agreement.csv \
		--out-dir $(ANALYSIS_OUT_DIR) \
		--tex-dir $(ANALYSIS_OUT_DIR) \
		--min-common 2

validate-results:
	$(DOCKER_BUILD_METRIC) -t jsonl-schema-validator:latest metrics/validate-results/generic/jsonl-schema-validator
	docker run --rm -v $(RESULTS_DIR):/results jsonl-schema-validator:latest

test-unit:
	python3 -m pytest tests/unit -q

test-docker-matrix:
	python3 tests/integration/run_docker_matrix_tests.py


clean:
	rm -rf $(RESULTS_DIR)/* $(RESULTS_NORMALIZED_DIR)/* $(ANALYSIS_OUT_DIR)/*


archive:
	git archive -o sw-metrics-collection-$(shell git rev-parse --short HEAD).zip HEAD

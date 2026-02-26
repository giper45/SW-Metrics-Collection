SRC_DIR := $(PWD)/src
RESULTS_DIR := $(PWD)/results
RESULTS_NORMALIZED_DIR := $(PWD)/results_normalized
ANALYSIS_OUT_DIR := $(PWD)/analysis_out
EXPERIMENT_RUN_ID := $(if $(METRIC_RUN_ID),$(METRIC_RUN_ID),$(shell python3 -c 'import uuid; print(uuid.uuid4())'))
DOCKER_RUN_METRIC := docker run --rm -e METRIC_RUN_ID=$(EXPERIMENT_RUN_ID) -v $(SRC_DIR):/app:ro -v $(RESULTS_DIR):/results

.PHONY: \
	collect-loc-cloc \
	collect-loc-tokei \
	collect-loc-scc \
	collect-normalized-loc-cloc \
	collect-cc-lizard \
	collect-cc-radon \
	collect-cc-ckjm \
	collect-ce-ca-jdepend \
	collect-ce-ca-ck-cbo \
	collect-i-jdepend \
	collect-i-ck-derived \
	collect-lcom-ck \
	collect-duplication-jscpd \
	collect-mi-halstead-java \
	collect-static-warnings-checkstyle \
	collect-coverage-jacoco \
	collect-churn-git \
	collect-size-all \
	collect-complexity-all \
	collect-coupling-all \
	collect-instability-all \
	collect-cohesion-all \
	collect-paper-extras \
	collect-all \
	clean-experiment \
	print-run-id \
	manifest \
	normalize \
	dataset \
	agreement \
	report \
	experiment \
	paper-tables \
	validate-results \
	test-unit \
	test-docker-matrix

collect-loc-cloc:
	docker build --build-context repo_common=$(PWD)/metrics/common -t loc-cloc:latest metrics/size/generic/loc-cloc
	$(DOCKER_RUN_METRIC) loc-cloc:latest

collect-loc-tokei:
	docker build --build-context repo_common=$(PWD)/metrics/common -t loc-tokei:latest metrics/size/generic/loc-tokei
	$(DOCKER_RUN_METRIC) loc-tokei:latest

collect-loc-scc:
	docker build --build-context repo_common=$(PWD)/metrics/common -t loc-scc:latest metrics/size/generic/loc-scc
	$(DOCKER_RUN_METRIC) loc-scc:latest

collect-normalized-loc-cloc:
	docker build --build-context repo_common=$(PWD)/metrics/common -t normalized-collector:latest metrics/generic/normalized-collector
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
	docker build --build-context repo_common=$(PWD)/metrics/common -t cc-lizard:latest metrics/complexity/generic/cc-lizard
	$(DOCKER_RUN_METRIC) cc-lizard:latest

collect-cc-radon:
	docker build --build-context repo_common=$(PWD)/metrics/common -t cc-radon:latest metrics/complexity/python/cc-radon
	$(DOCKER_RUN_METRIC) cc-radon:latest

collect-cc-ckjm:
	docker build --build-context repo_common=$(PWD)/metrics/common -t cc-ckjm:latest metrics/complexity/java/cc-ckjm
	$(DOCKER_RUN_METRIC) cc-ckjm:latest

collect-ce-ca-jdepend:
	docker build --build-context repo_common=$(PWD)/metrics/common -t ce-ca-jdepend:latest metrics/coupling/java/ce-ca-jdepend
	$(DOCKER_RUN_METRIC) ce-ca-jdepend:latest

collect-ce-ca-ck-cbo:
	docker build --build-context repo_common=$(PWD)/metrics/common -t ce-ca-ck-cbo:latest metrics/coupling/java/ce-ca-ck-cbo
	$(DOCKER_RUN_METRIC) ce-ca-ck-cbo:latest

collect-i-jdepend:
	docker build --build-context repo_common=$(PWD)/metrics/common -t i-jdepend:latest metrics/instability/java/i-jdepend
	$(DOCKER_RUN_METRIC) i-jdepend:latest

collect-i-ck-derived:
	docker build --build-context repo_common=$(PWD)/metrics/common -t i-ck-derived:latest metrics/instability/java/i-ck-derived
	$(DOCKER_RUN_METRIC) i-ck-derived:latest

collect-lcom-ck:
	docker build --build-context repo_common=$(PWD)/metrics/common -t lcom-ck:latest metrics/cohesion/java/lcom-ck
	$(DOCKER_RUN_METRIC) lcom-ck:latest

collect-duplication-jscpd:
	docker build --build-context repo_common=$(PWD)/metrics/common -t duplication-jscpd:latest metrics/duplication/java/duplication-jscpd
	$(DOCKER_RUN_METRIC) duplication-jscpd:latest

collect-mi-halstead-java:
	docker build --build-context repo_common=$(PWD)/metrics/common -t mi-halstead-java:latest metrics/maintainability/java/mi-halstead-java
	$(DOCKER_RUN_METRIC) mi-halstead-java:latest

collect-static-warnings-checkstyle:
	docker build --build-context repo_common=$(PWD)/metrics/common -t static-warnings-checkstyle:latest metrics/quality/java/static-warnings-checkstyle
	$(DOCKER_RUN_METRIC) static-warnings-checkstyle:latest

collect-coverage-jacoco:
	docker build --build-context repo_common=$(PWD)/metrics/common -t coverage-jacoco:latest metrics/testing/java/coverage-jacoco
	$(DOCKER_RUN_METRIC) coverage-jacoco:latest

collect-churn-git:
	docker build --build-context repo_common=$(PWD)/metrics/common -t churn-git:latest metrics/evolution/generic/churn-git
	$(DOCKER_RUN_METRIC) churn-git:latest

collect-size-all: collect-loc-cloc collect-loc-tokei collect-loc-scc
collect-complexity-all: collect-cc-lizard collect-cc-ckjm
collect-coupling-all: collect-ce-ca-jdepend collect-ce-ca-ck-cbo
collect-instability-all: collect-i-jdepend collect-i-ck-derived
collect-cohesion-all: collect-lcom-ck
collect-paper-extras: collect-duplication-jscpd collect-mi-halstead-java collect-static-warnings-checkstyle collect-coverage-jacoco collect-churn-git

clean-experiment:
	rm -rf $(RESULTS_DIR) $(RESULTS_NORMALIZED_DIR) $(ANALYSIS_OUT_DIR)
	mkdir -p $(RESULTS_DIR) $(RESULTS_NORMALIZED_DIR) $(ANALYSIS_OUT_DIR)

print-run-id:
	@echo "Using METRIC_RUN_ID=$(EXPERIMENT_RUN_ID)"

collect-all: print-run-id collect-size-all collect-complexity-all collect-coupling-all collect-instability-all collect-cohesion-all collect-paper-extras

manifest:
	python3 -m analysis.build_manifest \
		--results-dir $(RESULTS_DIR) \
		--run-id $(EXPERIMENT_RUN_ID) \
		--out $(RESULTS_DIR)/manifest-$(EXPERIMENT_RUN_ID).json \
		--primary-component-type file \
		--language java \
		--expected 'loc:cloc:cloc-default,loc:tokei:tokei-default,loc:scc:scc-default,cc:lizard:lizard-default,wmc:ckjm:ckjm-raw,nom:ckjm:ckjm-raw,ce-ca:jdepend:jdepend-default,cbo:ck:ck-cbo-agg,instability:jdepend:jdepend-default,instability:ck:ck-derived,lcom:ck:ck-default,duplication-rate:jscpd:jscpd-default,maintainability-index:java-halstead-analyzer:mi-halstead-default,static-warnings:checkstyle:checkstyle-default,test-coverage:jacoco:jacoco-default,code-churn:git:git-default'

normalize:
	python3 -m analysis.normalize $(RESULTS_DIR) $(RESULTS_NORMALIZED_DIR)

dataset:
	python3 -m analysis.build_dataset --in $(RESULTS_NORMALIZED_DIR) --out $(ANALYSIS_OUT_DIR) --wide-component-type file

agreement:
	python3 -m analysis.agreement --in $(ANALYSIS_OUT_DIR)/dataset_long.csv --out $(ANALYSIS_OUT_DIR)/agreement.csv

report:
	python3 -m analysis.report_repository --normalized $(RESULTS_NORMALIZED_DIR) --long $(ANALYSIS_OUT_DIR)/dataset_long.csv --out $(ANALYSIS_OUT_DIR)/repo_report.csv --out-json $(ANALYSIS_OUT_DIR)/repo_report.json

experiment: clean-experiment collect-all manifest normalize dataset agreement report

paper-tables:
	@echo "paper-tables target is not implemented yet; add analysis/paper_tables.py then wire it here."

validate-results:
	docker build --build-context repo_common=$(PWD)/metrics/common -t jsonl-schema-validator:latest metrics/validate-results/generic/jsonl-schema-validator
	docker run --rm -v $(RESULTS_DIR):/results jsonl-schema-validator:latest

test-unit:
	python3 -m pytest tests/unit -q

test-docker-matrix:
	python3 tests/integration/run_docker_matrix_tests.py


clean:
	rm -rf $(RESULTS_DIR)/* $(RESULTS_NORMALIZED_DIR)/* $(ANALYSIS_OUT_DIR)/*

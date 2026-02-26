# syntax=docker/dockerfile:1.4
FROM python:3.11-slim

ARG TOOL_PACKAGE=cloc

RUN apt-get update \
    && apt-get install -y --no-install-recommends ${TOOL_PACKAGE} \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/collector
COPY collect.py validator.py run.sh ./
COPY --from=repo_common result_writer.py /opt/collector/common/result_writer.py
RUN chmod +x /opt/collector/run.sh

ENV APP_ROOT=/app
ENV RESULTS_ROOT=/results
ENV SCHEMA_VERSION=1.0
ENV METRIC_KEY=loc
ENV TOOL_KEY=cloc
ENV COMMAND="cloc --json --quiet --skip-uniqueness {project_path}"
ENV TOOL_VERSION_COMMAND="cloc --version"
ENV ENTITY_TYPE=project
ENV VARIANT_KEY=default
ENV SCOPE_FILTER=no_tests
ENV CONTAINER_IMAGE=normalized-collector:latest

ENTRYPOINT ["/opt/collector/run.sh"]

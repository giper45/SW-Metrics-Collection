# syntax=docker/dockerfile:1.4
FROM python:3.11-slim

ARG CHECKSTYLE_VERSION=10.17.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl default-jre-headless \
    && mkdir -p /opt/tools \
    && curl -fsSL -o /opt/tools/checkstyle.jar \
      "https://github.com/checkstyle/checkstyle/releases/download/checkstyle-${CHECKSTYLE_VERSION}/checkstyle-${CHECKSTYLE_VERSION}-all.jar" \
    && rm -rf /var/lib/apt/lists/*

ENV CHECKSTYLE_VERSION=${CHECKSTYLE_VERSION}

WORKDIR /opt/metric
COPY collect.py run.sh checkstyle.xml ./
COPY --from=repo_common result_writer.py /opt/metric/common/result_writer.py
COPY --from=repo_common result_executor.py /opt/metric/common/result_executor.py
RUN chmod +x /opt/metric/run.sh

ENTRYPOINT ["/opt/metric/run.sh"]

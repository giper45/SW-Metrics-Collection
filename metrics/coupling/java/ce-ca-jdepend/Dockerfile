# syntax=docker/dockerfile:1.4
FROM python:3.11-slim

RUN pip install --no-cache-dir numpy pandas

ARG JDEPEND_VERSION=2.9.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl default-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/tools \
    && curl -fsSL -o /opt/tools/jdepend.jar \
      "https://repo1.maven.org/maven2/jdepend/jdepend/${JDEPEND_VERSION}/jdepend-${JDEPEND_VERSION}.jar"

ENV JDEPEND_VERSION=${JDEPEND_VERSION}

WORKDIR /opt/metric
COPY collect.py run.sh ./
COPY --from=repo_common *.py /opt/metric/common/
RUN chmod +x /opt/metric/run.sh

ENTRYPOINT ["/opt/metric/run.sh"]

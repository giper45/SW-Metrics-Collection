# syntax=docker/dockerfile:1.4
FROM python:3.11-slim

RUN pip install --no-cache-dir numpy pandas

ARG JAVAPARSER_VERSION=3.26.3

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl default-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/metric
COPY collect.py run.sh JavaInventoryTool.java ./
RUN mkdir -p /opt/metric/lib /opt/metric/bin \
    && curl -fsSL -o /opt/metric/lib/javaparser-core.jar \
        "https://repo1.maven.org/maven2/com/github/javaparser/javaparser-core/${JAVAPARSER_VERSION}/javaparser-core-${JAVAPARSER_VERSION}.jar" \
    && javac -cp /opt/metric/lib/javaparser-core.jar -d /opt/metric/bin /opt/metric/JavaInventoryTool.java

COPY --from=repo_common *.py /opt/metric/common/
ENV PYTHONPATH="/opt/metric/common"
ENV JAVA_INVENTORY_CLASSPATH="/opt/metric/bin:/opt/metric/lib/javaparser-core.jar"
ENV JAVA_INVENTORY_MAIN_CLASS="JavaInventoryTool"
ENV JAVAPARSER_VERSION="${JAVAPARSER_VERSION}"

RUN chmod +x /opt/metric/run.sh

ENTRYPOINT ["/opt/metric/run.sh"]

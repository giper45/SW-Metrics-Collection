# syntax=docker/dockerfile:1.4
FROM python:3.11-slim

RUN pip install --no-cache-dir numpy pandas

ARG CK_VERSION=0.7.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/tools \
    && curl -fsSL -o /opt/tools/ck.jar \
      "https://repo1.maven.org/maven2/com/github/mauricioaniche/ck/${CK_VERSION}/ck-${CK_VERSION}-jar-with-dependencies.jar"

ENV CK_VERSION=${CK_VERSION}

WORKDIR /opt/metric
COPY collect.py run.sh ./
COPY --from=repo_common *.py /opt/metric/common/
RUN chmod +x /opt/metric/run.sh

ENTRYPOINT ["/opt/metric/run.sh"]

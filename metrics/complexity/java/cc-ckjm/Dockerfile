# syntax=docker/dockerfile:1.4
FROM python:3.11-slim

ARG CKJM_VERSION=1.9
ARG BCEL_VERSION=5.2
ARG CK_VERSION=0.7.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl default-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/tools \
    && curl -fsSL -o /opt/tools/ckjm.jar \
      "https://repo1.maven.org/maven2/gr/spinellis/ckjm/${CKJM_VERSION}/ckjm-${CKJM_VERSION}.jar"
RUN curl -fsSL -o /opt/tools/bcel.jar \
      "https://repo1.maven.org/maven2/org/apache/bcel/bcel/${BCEL_VERSION}/bcel-${BCEL_VERSION}.jar"
RUN curl -fsSL -o /opt/tools/ck.jar \
      "https://repo1.maven.org/maven2/com/github/mauricioaniche/ck/${CK_VERSION}/ck-${CK_VERSION}-jar-with-dependencies.jar"

ENV CKJM_VERSION=${CKJM_VERSION}
ENV BCEL_VERSION=${BCEL_VERSION}
ENV CK_VERSION=${CK_VERSION}

WORKDIR /opt/metric
COPY collect.py run.sh ./
COPY --from=repo_common result_writer.py /opt/metric/common/result_writer.py
RUN chmod +x /opt/metric/run.sh

ENTRYPOINT ["/opt/metric/run.sh"]

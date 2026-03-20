# syntax=docker/dockerfile:1.4
FROM python:3.11-slim

RUN pip install --no-cache-dir numpy pandas

ARG CKJM_REPO=https://github.com/dspinellis/ckjm.git
ARG CKJM_REF=7fb679444e08ec596523d3b05053fd045af515d7
ARG CKJM_BUILD_VERSION=local
ARG COMMONS_LANG3_VERSION=3.14.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends ant ca-certificates curl git default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 "${CKJM_REPO}" /tmp/ckjm-src \
    && cd /tmp/ckjm-src \
    && git fetch --depth 1 origin "${CKJM_REF}" \
    && git checkout "${CKJM_REF}" \
    && ant -Dversion="${CKJM_BUILD_VERSION}" compile \
    && mkdir -p /opt/tools \
    && cp /tmp/ckjm-src/build/ckjm-${CKJM_BUILD_VERSION}.jar /opt/tools/ckjm.jar \
    && curl -fsSL -o /opt/tools/commons-lang3.jar \
      "https://repo1.maven.org/maven2/org/apache/commons/commons-lang3/${COMMONS_LANG3_VERSION}/commons-lang3-${COMMONS_LANG3_VERSION}.jar" \
    && rm -rf /tmp/ckjm-src

ENV CKJM_VERSION=${CKJM_REF}

WORKDIR /opt/metric
COPY collect.py run.sh ./
COPY --from=repo_common *.py /opt/metric/common/
RUN chmod 644 /opt/metric/*.py \
    && chmod 644 /opt/metric/common/*.py \
    && chmod +x /opt/metric/run.sh

ENTRYPOINT ["/opt/metric/run.sh"]

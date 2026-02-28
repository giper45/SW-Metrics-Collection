# syntax=docker/dockerfile:1.4
FROM python:3.11-slim

ARG SCC_VERSION=3.2.0
ARG TARGETARCH

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl tar \
    && rm -rf /var/lib/apt/lists/*

RUN set -eu; \
    case "${TARGETARCH}" in \
      amd64) SCC_ARCH="x86_64" ;; \
      arm64) SCC_ARCH="arm64" ;; \
      *) echo "Unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /tmp/scc.tar.gz \
      "https://github.com/boyter/scc/releases/download/v${SCC_VERSION}/scc_Linux_${SCC_ARCH}.tar.gz" \
    && tar -xzf /tmp/scc.tar.gz -C /tmp \
    && mv /tmp/scc /usr/local/bin/scc \
    && chmod +x /usr/local/bin/scc \
    && rm -f /tmp/scc.tar.gz

WORKDIR /opt/metric
COPY collect.py run.sh ./
COPY --from=repo_common result_writer.py /opt/metric/common/result_writer.py
COPY --from=repo_common result_executor.py /opt/metric/common/result_executor.py
RUN chmod +x /opt/metric/run.sh

ENTRYPOINT ["/opt/metric/run.sh"]

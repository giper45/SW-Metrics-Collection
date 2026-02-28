# syntax=docker/dockerfile:1.4
FROM python:3.11-slim

ARG TOKEI_VERSION=12.1.2
ARG TARGETARCH

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN set -eu; \
    case "${TARGETARCH}" in \
      amd64) TOKEI_ARCH="x86_64-unknown-linux-gnu" ;; \
      arm64) TOKEI_ARCH="aarch64-unknown-linux-gnu" ;; \
      *) echo "Unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /tmp/tokei.tar.gz \
      "https://github.com/XAMPPRocky/tokei/releases/download/v${TOKEI_VERSION}/tokei-${TOKEI_ARCH}.tar.gz" \
    && tar -xzf /tmp/tokei.tar.gz -C /usr/local/bin tokei \
    && chmod +x /usr/local/bin/tokei \
    && rm -f /tmp/tokei.tar.gz

WORKDIR /opt/metric
COPY collect.py run.sh ./
COPY --from=repo_common result_writer.py /opt/metric/common/result_writer.py
COPY --from=repo_common result_executor.py /opt/metric/common/result_executor.py
RUN chmod +x /opt/metric/run.sh

ENTRYPOINT ["/opt/metric/run.sh"]

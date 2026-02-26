# syntax=docker/dockerfile:1.4
FROM python:3.11-slim

ARG SCC_VERSION=3.2.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl tar \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /tmp/scc.tar.gz \
      "https://github.com/boyter/scc/releases/download/v${SCC_VERSION}/scc_${SCC_VERSION}_Linux_x86_64.tar.gz" \
    && tar -xzf /tmp/scc.tar.gz -C /tmp \
    && mv /tmp/scc /usr/local/bin/scc \
    && chmod +x /usr/local/bin/scc \
    && rm -f /tmp/scc.tar.gz

WORKDIR /opt/metric
COPY collect.py run.sh ./
COPY --from=repo_common result_writer.py /opt/metric/common/result_writer.py
RUN chmod +x /opt/metric/run.sh

ENTRYPOINT ["/opt/metric/run.sh"]

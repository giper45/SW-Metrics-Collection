# syntax=docker/dockerfile:1.4
FROM python:3.11-slim

ARG JSCPD_VERSION=4.0.5

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates nodejs npm \
    && npm install -g "jscpd@${JSCPD_VERSION}" \
    && rm -rf /var/lib/apt/lists/*

ENV JSCPD_VERSION=${JSCPD_VERSION}

WORKDIR /opt/metric
COPY collect.py run.sh ./
COPY --from=repo_common result_writer.py /opt/metric/common/result_writer.py
RUN chmod +x /opt/metric/run.sh

ENTRYPOINT ["/opt/metric/run.sh"]

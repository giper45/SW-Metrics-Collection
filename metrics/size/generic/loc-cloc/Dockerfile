# syntax=docker/dockerfile:1.4
FROM python:3.11-slim

RUN pip install --no-cache-dir numpy pandas

RUN apt-get update \
    && apt-get install -y --no-install-recommends cloc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/metric
COPY collect.py run.sh ./
COPY --from=repo_common *.py /opt/metric/common/
RUN chmod 644 /opt/metric/*.py \
    && chmod 644 /opt/metric/common/*.py \
    && chmod +x /opt/metric/run.sh

ENTRYPOINT ["/opt/metric/run.sh"]

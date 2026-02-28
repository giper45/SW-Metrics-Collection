# syntax=docker/dockerfile:1.4
FROM python:3.11-slim

RUN pip install --no-cache-dir lizard

WORKDIR /work
COPY collect_metric.py /collect_metric.py
COPY --from=repo_common result_writer.py /common/result_writer.py
COPY --from=repo_common result_executor.py /common/result_executor.py

ENTRYPOINT ["python", "/collect_metric.py"]

# syntax=docker/dockerfile:1.4
FROM python:3.11-slim

RUN pip install --no-cache-dir lizard==1.17.10

WORKDIR /opt/metric
COPY collect.py run.sh ./
COPY --from=repo_common result_writer.py /opt/metric/common/result_writer.py
COPY --from=repo_common result_executor.py /opt/metric/common/result_executor.py
RUN chmod +x /opt/metric/run.sh

ENTRYPOINT ["/opt/metric/run.sh"]

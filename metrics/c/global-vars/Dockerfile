FROM python:3.11-slim

RUN pip install --no-cache-dir numpy pandas

WORKDIR /app
COPY collect-global-vars.py /collect-global-vars.py

ENTRYPOINT ["python", "/collect-global-vars.py", "/app", "/results"]

FROM python:3.11-slim

WORKDIR /app
COPY collect-global-vars.py /collect-global-vars.py

ENTRYPOINT ["python", "/collect-global-vars.py", "/app", "/results"]

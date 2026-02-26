FROM python:3.11-slim

RUN pip install --no-cache-dir lizard

WORKDIR /app
COPY collect-fan-in-out.py /collect-fan-in-out.py

ENTRYPOINT ["python", "/collect-fan-in-out.py", "/app", "/results"]

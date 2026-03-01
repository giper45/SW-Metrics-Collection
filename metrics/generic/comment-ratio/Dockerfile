FROM python:3.11-slim

RUN pip install --no-cache-dir numpy pandas

WORKDIR /app
COPY collect-comment-ratio.py /collect-comment-ratio.py

ENTRYPOINT ["python", "/collect-comment-ratio.py", "/app", "/results"]

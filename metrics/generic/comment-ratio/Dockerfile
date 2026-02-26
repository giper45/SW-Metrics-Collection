FROM python:3.11-slim

WORKDIR /app
COPY collect-comment-ratio.py /collect-comment-ratio.py

ENTRYPOINT ["python", "/collect-comment-ratio.py", "/app", "/results"]

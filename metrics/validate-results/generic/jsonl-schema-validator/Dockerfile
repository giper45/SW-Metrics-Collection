FROM python:3.11-slim

RUN pip install --no-cache-dir numpy pandas

WORKDIR /opt/validator
COPY validate.py ./

ENTRYPOINT ["python", "/opt/validator/validate.py"]

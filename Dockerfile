FROM docker:28-dind

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MAVIS_WEB_HOST=0.0.0.0 \
    MAVIS_WEB_PORT=9999

WORKDIR /workspace

RUN apk add --no-cache \
    bash \
    git \
    make \
    py3-pip \
    python3

COPY webapp/requirements.txt /tmp/webapp-requirements.txt
RUN python3 -m pip install --break-system-packages --no-cache-dir -r /tmp/webapp-requirements.txt

COPY docker/web-entrypoint.sh /usr/local/bin/mavis-web-entrypoint
RUN chmod +x /usr/local/bin/mavis-web-entrypoint

COPY . /workspace

EXPOSE 9999

ENTRYPOINT ["/usr/local/bin/mavis-web-entrypoint"]

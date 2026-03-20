# syntax=docker/dockerfile:1.4
ARG JAVA_VERSION=21
FROM eclipse-temurin:${JAVA_VERSION}-jdk

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ant \
        bash \
        ca-certificates \
        curl \
        gradle \
        git \
        maven \
        unzip \
        zip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

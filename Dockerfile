FROM alpine:latest
RUN apk --update add \
    git \
    py-pip \
    python \
    python-dev \
    gcc \
    build-base \
    libffi-dev \
    openssl \
    openssl-dev \
    musl-dev \
    libxml2-dev \
    libxslt-dev \
    libffi-dev \
    libxml2 \
    libxslt \
    py-setuptools \
    && rm -rf /var/cache/apk/*
RUN git clone https://github.com/PokemonAlpha/AlphaBot

WORKDIR /AlphaBot
RUN git checkout dev \
    && pip install -r requirements.txt
RUN wget -O encrypt.so https://github.com/PokemonGoMap/PokemonGo-Map/raw/develop/pogom/libencrypt/libencrypt-linux-x86-64.so \
    && mv encrypt.so configs/ 
RUN apk del \
    git \
    py-pip \
    python-dev \
    gcc \
    build-base \
    libffi-dev \
    openssl \
    openssl-dev \
    musl-dev \
    libxml2-dev \
    libxslt-dev \
    libffi-dev \
    libxml2 \
    libxslt 

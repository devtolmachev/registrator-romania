FROM rust:1-alpine3.20

RUN apk update && apk add openssl libressl-dev
RUN apk add python3 python3-dev
RUN apk add py3-pip

# ENV PYTHONUNBUFFERED=1
# RUN ln -sf python3 /usr/bin/python
# RUN python3 -m ensurepip
# RUN pip install --no-cache --upgrade pip setuptools

COPY bindings /app/bindings
WORKDIR /app/bindings
RUN cargo update
RUN pip install --break-system-packages maturin

RUN apk add --no-cache musl-dev && apk add --no-cache build-base
RUN pip install --break-system-packages 'maturin[patchelf]'
RUN maturin build --release

RUN pip install --break-system-packages `find . -name "*.whl" -type f`
RUN pip install --break-system-packages poetry

WORKDIR /app

COPY pyproject.toml /app/
RUN poetry config virtualenvs.create false
ENV PIP_BREAK_SYSTEM_PACKAGES=1
RUN poetry install --no-root --no-interaction --no-ansi

COPY . /app
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

ENTRYPOINT ["python", "-m", "registrator_romania"]
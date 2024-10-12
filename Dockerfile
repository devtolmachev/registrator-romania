FROM rust:1-alpine3.20 AS rust_builder

# install packages
RUN apk update && apk add openssl libressl-dev musl-dev build-base python3 python3-dev py3-pip

# allow installing python libs to root
ENV PIP_BREAK_SYSTEM_PACKAGES=1
# change directory
WORKDIR /app

# install deps for rust bindings
RUN pip install 'maturin[patchelf]'
# build bindings
COPY bindings /app/bindings
WORKDIR /app/bindings
RUN cargo update
RUN maturin build --release

FROM python:3.12-alpine3.20
# install python dependencies
RUN pip install poetry
COPY pyproject.toml /app/
WORKDIR /app
RUN poetry config virtualenvs.create false
RUN poetry install --no-root --no-interaction --no-ansi

COPY --from=rust_builder /app/bindings/target/wheels /wheels
RUN pip install `find /wheels -name "*.whl" -type f`

# set working directory
WORKDIR /app
# copy code
COPY . /app
# set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

ENTRYPOINT ["python", "-m", "registrator_romania"]
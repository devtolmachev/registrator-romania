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

# install python dependencies
COPY pyproject.toml /app/
RUN poetry config virtualenvs.create false
RUN poetry install --no-root --no-interaction --no-ansi

RUN pip install `find . -name "*.whl" -type f`

# set working directory
WORKDIR /app
# copy code
COPY . /app
# set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

ENTRYPOINT ["python", "-m", "registrator_romania"]
FROM python:3.13-slim

# Alternatives for APP_ENV:
# - production: for production deployment
# - development: for local develpment environment
# - ci: for continous integration environment

RUN adduser --system --no-create-home --home=/app app

COPY requirements.txt /
RUN apt-get update && \
  apt-get install -y build-essential && \
  pip install uv==0.12.8 && \
  uv pip install --system -r /requirements.txt && \
  uv cache clean && \
  apt-get clean

ARG APP_ENV="production"
ENV APP_ENV $APP_ENV

COPY requirements-dev.txt /
RUN if [ $APP_ENV != "production" ]; then \
  uv pip install --system -r /requirements-dev.txt && \
  uv cache clean; \
  fi

COPY . /app
WORKDIR /app

# Required since we don't copy the .git folder into the image.
# Production image should be built with `--arg=DOCKER_METADATA_OUTPUT_VERSION=$(python setup.py --version)` to inject the correct version into the package.
ARG DOCKER_METADATA_OUTPUT_VERSION=0.0.1-beta1
ENV SETUPTOOLS_SCM_PRETEND_VERSION=$DOCKER_METADATA_OUTPUT_VERSION

RUN if [ $APP_ENV = "production" ]; then \
  uv pip install --system . \
  && uv cache clean \
  && rm -rf /app \
  && mkdir -p /app; \
  else \
  uv pip install --system -e . \
  && uv cache clean; \
  fi


EXPOSE 8000

USER app

ENTRYPOINT ["python", "-m", "eth_exporter.exporter"]

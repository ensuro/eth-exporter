FROM python:3.10-slim

# Alternatives for APP_ENV:
# - production: for production deployment
# - development: for local develpment environment
# - ci: for continous integration environment

RUN adduser --system --no-create-home --home=/app app

ARG APP_ENV="production"
ENV APP_ENV $APP_ENV

COPY . /app
WORKDIR /app

# Required since we don't copy the .git folder into the image.
# Production image should be built with `--arg=DOCKER_METADATA_OUTPUT_VERSION=$(python setup.py --version)` to inject the correct version into the package.
ARG DOCKER_METADATA_OUTPUT_VERSION=0.0.1-beta1
ENV SETUPTOOLS_SCM_PRETEND_VERSION=$DOCKER_METADATA_OUTPUT_VERSION

RUN if [ $APP_ENV = "production" ]; then \
        pip install . \
            && rm -rf /app \
            && mkdir -p /app; \
    else \
        pip install -e .; \
    fi


EXPOSE 8000

USER app

ENTRYPOINT ["python", "-m", "eth_exporter.exporter"]

# eth-exporter

Prometheus exporter of blockchain data

## Development

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/):

```sh
pip install uv
uv pip install -e . -r requirements.txt -r requirements-dev.txt

uv pip compile requirements.in       # refresh pinned deps
uv pip compile requirements-dev.in

ruff check .    # lint
ruff format .   # format (black-compatible, line-length 120)
tox -e py       # run tests
```

Dependency resolution ignores releases newer than 14 days (`exclude-newer` in `pyproject.toml`).

## Running with docker

A `compose.yaml` file is provided to run the app + prometheus and grafana in docker.

1. Copy the sample config to be used: `cp .env.sample .env`
2. Start the containers:  `docker compose up`
3. Services will be available on these urls:
  - Exporter: http://localhost:8000/metrics
  - Prometheus: http://localhost:9090
  - Grafana: http://localhost:3000 (credentials admin:grafana)

<!-- pyscaffold-notes -->

## Note

This project has been set up using PyScaffold 4.5. For details and usage
information on PyScaffold see https://pyscaffold.org/.

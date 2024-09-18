# eth-exporter

Prometheus exporter of blockchain data

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

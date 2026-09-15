# AGENTS.md

## Developer Commands

```bash
# Install dependencies (uses uv; pins are compiled from requirements*.in)
pip install uv
uv pip install -e . -r requirements.txt -r requirements-dev.txt
uv pip compile requirements.in         # refresh pinned deps
uv pip compile requirements-dev.in     # dev deps (constrains against requirements.txt)

# Run tests (via tox or pytest directly)
tox -e py                    # CI-style test run (uses uv via tox-uv-bare)
pytest tests/                # run all tests
pytest -k "test_erc20"       # single test by name

# Code quality (pre-commit hooks auto-run on commit)
ruff check .    # lint
ruff format .   # format (black-compatible, line-length 120)
pre-commit run --all-files
```

## Architecture

- **Entrypoint**: `python -m eth_exporter.exporter` (`exporter.py`)
- **Flow**: `main_loop()` (producer) queues new blocks from the node into an `asyncio.Queue`; `blocks_worker()` (consumer) fans out the contract calls defined by the metrics config.
- **Reorg safety**: reads the `BLOCK_COMMITMENT_LEVEL` block (default `"finalized"`) instead of `latest`; guarded by `MAX_BLOCK_AGE`.
- **Metrics config**: YAML file (`METRICS_CONFIG_PATH`) parsed by `metric_config.MetricsConfig`. Custom blocks are registered via `HandlerRegistry` (`erc20_balance`, `erc4626_balance`, `pa_loans`); plain `calls` are loaded directly. Each call maps contract return fields to Prometheus metrics.
- **Contract interaction**: `chaindata.ContractCall` (single RPC calls) and `chaindata.ContractCallMulticall3` (batched via `multicall3.aggregate3`, enabled with `USE_MULTICALL3`).
- **Address resolution**: `vendor.address_book` (name <-> address) and `vendor.build_artifacts.ArtifactLibrary` (ABIs from `ABIS_PATH`).
- **Config**: environment variables via `environs` (see `config.py`); optional `.env`/`ENV_FILE_TO_READ`.
- **Metrics**: `metrics.py` defines global gauges/histograms plus an RPC middleware (`RPCMetricsMiddleware`) and an asyncio monitor (`AIOMonitor`).

## Style & Tools

- **Formatter**: ruff format with `line-length = 120` (black-compatible; see `pyproject.toml`)
- **Import sorting**: ruff isort rules with `known-first-party = ["eth_exporter"]` (`.isort.cfg` removed during the ruff migration)
- **Linting**: ruff check, `select = ["E", "W", "F", "I"]`, ignoring E203 (W503 is not implemented by ruff)
- **Coverage**: Configured in `setup.cfg` (`--cov eth_exporter`); `.coveragerc` source is `eth_exporter`

## Dependency Management

- **Requirements**: `requirements.in` -> `requirements.txt` (compiled with `uv pip compile`; targets the active venv's Python, governed by `.python-version`)
- **Dev requirements**: `requirements-dev.in` -> `requirements-dev.txt` (constrains against requirements.txt)
- **Reproducibility**: `[tool.uv] exclude-newer = "14 days"` in pyproject.toml - resolution ignores releases newer than 14 days
- **Runtime deps live in `requirements.in`** (mirrors the bridge23 layout); `setup.cfg` `install_requires` is intentionally minimal
- **Extras**: Test deps defined in `setup.cfg` `[options.extras_require] testing`

## Docker

- **Build**: Pass `DOCKER_METADATA_OUTPUT_VERSION` build-arg to set version (image lacks `.git` dir)
- **Entrypoint**: `python -m eth_exporter.exporter`
- **Env**: `APP_ENV=production|development|ci` controls dev dependencies installation
- **Installs**: deps and project installed with `uv pip install --system` (uv pinned to match requirements-dev.txt); `uv cache clean` keeps the image lean

## CI

- **Tests**: GitHub Actions runs `tox -e py` on Python 3.13; tox installs deps via uv (`tox-uv-bare` plugin, see tox.ini)
- **Secrets scan**: Gitleaks runs on every push
- **Vulnerability scan**: OSV-Scanner on PRs, merge groups, and a weekly schedule (see `osv-scanner.toml`)
- **Docker build**: Triggered by version tags (`v*`) via `build-push-image.yaml`, pushes to `us-docker.pkg.dev/solid-range-319205/ensuro/eth-exporter`

## Known Legacy References

- `.isort.cfg` was removed during the ruff migration; `known_first_party` is now `eth_exporter` in `pyproject.toml`
- `.coveragerc` previously referenced the stale `blockchain_exporter` package name; corrected to `eth_exporter`

import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone

from prometheus_async.aio import time as prom_time
from prometheus_async.aio.web import start_http_server_in_thread
from web3 import AsyncWeb3
from web3.middleware import ExtraDataToPOAMiddleware, validation
from web3.providers import AsyncHTTPProvider

from . import config, metrics
from .chaindata import MetricsConfig
from .vendor import address_book

logger = logging.getLogger(__name__)


def age(timestamp):
    return time.monotonic() - timestamp


async def main_loop(w3, queue):
    """Producer that queues new blocks for metrics processing."""
    last_block = None
    last_block_timestamp = 0
    while True:
        block_age = age(last_block_timestamp)
        if block_age > config.MAX_BLOCK_AGE:
            # Get the 'safe' block instead of the 'latest', to protect the metrics against reorgs
            new_block = await w3.eth.get_block(config.BLOCK_COMMITMENT_LEVEL)
            if last_block is not None and new_block.number == last_block.number:
                logger.warning(
                    "Block %s is stale (%.2f seconds old), but no new blocks are available yet",
                    new_block.number,
                    block_age,
                )
            else:
                last_block = new_block
                last_block_timestamp = time.monotonic()
                await queue.put(last_block)

        await asyncio.sleep(config.BLOCK_REFRESH_INTERVAL)


async def blocks_worker(w3: AsyncWeb3, queue: asyncio.Queue, metrics_config: MetricsConfig):
    """Consumer that triggers the contract calls for each block"""
    sem = asyncio.Semaphore(config.MAX_CONCURRENT_CALLS)

    while True:
        block = await queue.get()

        logger.info(
            "Processing block %s - %s",
            block.number,
            datetime.fromtimestamp(block.timestamp, tz=timezone.utc).isoformat(),
        )

        calls = [call(w3, block, sem) for call in metrics_config.calls]
        await prom_time(metrics.BLOCK_PROCESSING_HISTOGRAM, asyncio.gather(*calls))

        metrics.LAST_BLOCK_TIMESTAMP.set(block.timestamp)
        metrics.LAST_BLOCK.set(block.number)

        queue.task_done()


def load_address_book(path):
    with open(path, "r") as f:
        mapping = json.load(f)
        address_book.setup_default(address_book.AddrToNameAddressBook(mapping))


async def main():
    if config.ADDRESS_BOOK_PATH:
        load_address_book(config.ADDRESS_BOOK_PATH)

    # Monitor some basic asyncio metrics to keep an eye on blocking code
    metrics.AIOMonitor().start()

    blocks_queue = asyncio.Queue()

    # Load the metrics definitions, this takes care of initializing the metrics to avoid missing metrics:
    # https://prometheus.io/docs/practices/instrumentation/#avoid-missing-metrics
    metrics_config = MetricsConfig.load_yaml(config.METRICS_CONFIG_PATH)

    # Set up the prometheus server
    prom_server = start_http_server_in_thread(port=config.METRICS_PORT)
    logger.info("Started metrics server on %s", prom_server.url)

    w3 = AsyncWeb3(AsyncHTTPProvider(config.NODE_HTTPS_URL, cache_allowed_requests=True))

    # Disable method validation to reduce eth_chainId calls
    validation.METHODS_TO_VALIDATE = []

    # Inject the middleware to track RPC calls with prometheus
    w3.middleware_onion.inject(metrics.RPCMetricsMiddleware, layer=0)
    # Inject the poa middleware if necessary
    if config.INJECT_POA_MIDDLEWARE:
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    # Create the main consumer
    worker = asyncio.create_task(blocks_worker(w3, blocks_queue, metrics_config))

    # Run the producer loop forever
    try:
        await asyncio.gather(main_loop(w3, blocks_queue), worker)
    finally:
        logger.info("Shutting down")
        prom_server.close()
        worker.cancel()


def main_sync():
    logging.basicConfig(level=config.LOG_LEVEL)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)  # 128 + SIGINT


if __name__ == "__main__":
    main_sync()

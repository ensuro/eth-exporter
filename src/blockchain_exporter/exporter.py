import asyncio
import logging
import time

from prometheus_async.aio.web import start_http_server
from web3 import AsyncWeb3
from web3.providers.persistent import WebSocketProvider

from . import config, metrics

logger = logging.getLogger(__name__)


def is_expired(timestamp):
    return time.monotonic() - timestamp > config.METRICS_REFRESH_INTERVAL_SECONDS


async def main_loop(w3, queue):
    """Producer that queues new blocks for metrics processing."""
    last_block = None
    last_block_timestamp = 0
    while True:
        if is_expired(last_block_timestamp):
            # Get the 'safe' block instead of the 'latest', to protect the metrics against reorgs
            last_block = await w3.eth.get_block("safe")
            last_block_timestamp = time.monotonic()
            await queue.put(last_block)

        await asyncio.sleep(1)


async def blocks_worker(w3, queue):
    """Consumer that triggers the calls for each block"""
    while True:
        block = await queue.get()

        metrics.LAST_BLOCK_TIMESTAMP.set(block.timestamp)
        metrics.LAST_BLOCK.set(block.number)
        metrics.BLOCKS_PROCESSED.inc()

        queue.task_done()


async def main():
    blocks_queue = asyncio.Queue()

    # TODO: at this point we should parse the config and initialize all metrics for it to avoid missing metrics:
    # https://prometheus.io/docs/practices/instrumentation/#avoid-missing-metrics

    async with AsyncWeb3(WebSocketProvider(config.NODE_WEBSOCKET_URL)) as w3:
        # Create the main consumer
        worker = asyncio.create_task(blocks_worker(w3, blocks_queue))

        # Set up the prometheus server
        prom_server = await start_http_server(port=config.METRICS_PORT)
        logger.info("Started metrics server on %s", prom_server.url)

        # Run the main loop forever
        await main_loop(w3, blocks_queue)

    logger.info("Shutting down")
    worker.cancel()
    prom_server.close()


if __name__ == "__main__":
    logging.basicConfig(level="INFO")

    asyncio.run(main())

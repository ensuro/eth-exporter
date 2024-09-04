import asyncio
import logging
import time
from datetime import datetime, timezone

from prometheus_async.aio.web import start_http_server
from web3 import AsyncWeb3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.providers.persistent import WebSocketProvider

from . import config, metrics
from .chaindata import ContractCall

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


async def blocks_worker(w3, queue):
    """Consumer that triggers the calls for each block"""
    while True:
        block = await queue.get()

        logger.info(
            "Processing block %s - %s",
            block.number,
            datetime.fromtimestamp(block.timestamp, tz=timezone.utc).isoformat(),
        )

        metrics.LAST_BLOCK_TIMESTAMP.set(block.timestamp)
        metrics.LAST_BLOCK.set(block.number)
        metrics.BLOCKS_PROCESSED.inc()

        call = ContractCall(
            "SignedBucketRiskModule",
            "params",
            [],
            [
                "0x43882aDe3Df425D7097f0ca62E8cf08E6bef8777",
                "0xe64b6B463c3B3Cb3475fb940B64Ef6f946D6F460",
            ],
        )

        results = await call(w3)
        logger.info("Results: %s", "\n".join(str(r) for r in results))

        queue.task_done()


async def main():
    blocks_queue = asyncio.Queue()

    # TODO: at this point we should parse the config and initialize all metrics, to avoid missing metrics:
    # https://prometheus.io/docs/practices/instrumentation/#avoid-missing-metrics

    # Set up the prometheus server
    prom_server = await start_http_server(port=config.METRICS_PORT)
    logger.info("Started metrics server on %s", prom_server.url)

    async with AsyncWeb3(WebSocketProvider(config.NODE_WEBSOCKET_URL)) as w3:
        # Inject the middleware to track RPC calls with prometheus
        w3.middleware_onion.inject(metrics.RPCMetricsMiddleware, layer=0)

        # Inject the poa middleware if necessary
        if config.INJECT_POA_MIDDLEWARE:
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        # Create the main consumer
        worker = asyncio.create_task(blocks_worker(w3, blocks_queue))

        # Run the producer loop forever
        try:
            await asyncio.gather(main_loop(w3, blocks_queue), worker)
        finally:
            logger.info("Shutting down")
            worker.cancel()
            await prom_server.close()


if __name__ == "__main__":
    logging.basicConfig(level="INFO")

    asyncio.run(main())

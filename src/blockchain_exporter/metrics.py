from prometheus_async.aio import time, track_inprogress
from prometheus_client import Counter, Gauge, Histogram
from web3.middleware import Web3Middleware

# Some basic global metrics

LAST_BLOCK = Gauge("last_block", "Last block number")
LAST_BLOCK_TIMESTAMP = Gauge("last_block_timestamp_seconds", "Last block timestamp")

BLOCKS_PROCESSED = Counter("blocks_processed", "Number of blocks processed")

RPC_CALLS_HISTOGRAM = Histogram("rpc_calls_duration_seconds", "Duration of rpc calls")

RPC_CALLS_IN_FLIGHT = Gauge("rpc_calls_in_flight", "Number of rpc calls in flight")


class RPCMetricsMiddleware(Web3Middleware):
    """Middleware to feed metrics of rpc call count and timing"""

    async def async_wrap_make_request(self, make_request):
        @time(RPC_CALLS_HISTOGRAM)
        @track_inprogress(RPC_CALLS_IN_FLIGHT)
        async def middleware(method, params):
            return await make_request(method, params)

        return middleware

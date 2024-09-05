import asyncio
from typing import List, Literal

from prometheus_async.aio import time, track_inprogress
from prometheus_client import Gauge, Histogram
from web3.middleware import Web3Middleware

# Some basic global metrics
LAST_BLOCK = Gauge("last_block", "Last block number")
LAST_BLOCK_TIMESTAMP = Gauge("last_block_timestamp_seconds", "Last block timestamp")

BLOCK_PROCESSING_HISTOGRAM = Histogram("block_processing_duration_seconds", "Duration of block processing")

RPC_CALLS_HISTOGRAM = Histogram("rpc_calls_duration_seconds", "Duration of rpc calls", ["method"])

RPC_CALLS_IN_FLIGHT = Gauge("rpc_calls_in_flight", "Number of rpc calls in flight", ["method"])


class RPCMetricsMiddleware(Web3Middleware):
    """Middleware to feed metrics of rpc call count and timing"""

    async def async_wrap_make_request(self, make_request):
        async def middleware(method, params):
            ret = make_request(method, params)
            ret = time(RPC_CALLS_HISTOGRAM.labels(method=method), ret)
            ret = track_inprogress(RPC_CALLS_IN_FLIGHT.labels(method=method), ret)
            return await ret

        return middleware


class AIOMonitor:
    """A class to monitor some basic asyncio metrics

    Based on Steve Brazier (MeadSteve)'s blog and adapted for prometheus monitoring:
    https://blog.meadsteve.dev/programming/2020/02/23/monitoring-async-python/
    """

    def __init__(self, interval: float = 1.0):
        self.interval = interval

        self.lag = Gauge("asyncio_lag_seconds", "Lag of the asyncio loop")
        self.active_tasks = Gauge("asyncio_active_tasks", "Number of active tasks in the asyncio loop")

    def start(self):
        loop = asyncio.get_running_loop()
        return loop.create_task(self._monitor_loop(loop))

    async def _monitor_loop(self, loop: asyncio.AbstractEventLoop):
        while loop.is_running():
            start = loop.time()  # monotonic loop time
            await asyncio.sleep(self.interval)
            time_slept = loop.time() - start
            self.lag.set(time_slept - self.interval)

            self.active_tasks.set(len([t for t in asyncio.all_tasks() if not t.done()]))


_metrics = {}


def create_metric(name: str, description: str, type: Literal["GAUGE"], labels: List[str] = None):
    if type == "GAUGE":
        if name not in _metrics:
            _metrics[name] = Gauge(name, description, labels if labels is not None else [])
        # TODO: validate description and labels match the existing metric
        return _metrics[name]
    else:
        raise NotImplementedError(f"Metric type {type} not implemented yet")

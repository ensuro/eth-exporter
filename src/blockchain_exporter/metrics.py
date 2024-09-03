from prometheus_client import Counter, Gauge

# Some basic global metrics

LAST_BLOCK = Gauge("last_block", "Last block number")
LAST_BLOCK_TIMESTAMP = Gauge("last_block_timestamp", "Last block timestamp")

BLOCKS_PROCESSED = Counter("blocks_processed", "Number of blocks processed")

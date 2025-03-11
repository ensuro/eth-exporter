import environs

env = environs.Env()

# Load dotenv, optionally from a file specified in the environment
env.read_env(path=env.str("ENV_FILE_TO_READ", None))

LOG_LEVEL = env.str("LOG_LEVEL", "INFO")

MAX_BLOCK_AGE = env.int("MAX_BLOCK_AGE", 60)

BLOCK_REFRESH_INTERVAL = env.int("BLOCK_REFRESH_INTERVAL", 30)
BLOCK_COMMITMENT_LEVEL = env.str("BLOCK_COMMITMENT_LEVEL", "finalized")

INJECT_POA_MIDDLEWARE = env.bool("INJECT_POA_MIDDLEWARE", False)

# NODE_WEBSOCKET_URL = env.str("NODE_WEBSOCKET_URL", None)
NODE_HTTPS_URL = env.str("NODE_HTTPS_URL", None)

METRICS_PORT = env.int("METRICS_PORT", 8000)


ABIS_PATH = env.str("ABIS_PATH", None)

USE_MULTICALL3 = env.bool("USE_MULTICALL3", False)


METRICS_CONFIG_PATH = env.str("METRICS_CONFIG_PATH", None)

ADDRESS_BOOK_PATH = env.str("ADDRESS_BOOK_PATH", None)

# Limit the number of concurrent calls to the node. Going over 12 is likely to exceed Alchemy's rate
# limit of 330CU/s on the free tier.
MAX_CONCURRENT_CALLS = env.int("MAX_CONCURRENT_CALLS", 4)

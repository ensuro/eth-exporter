import environs

env = environs.Env()

# Load dotenv, optionally from a file specified in the environment
env.read_env(path=env.str("ENV_FILE_TO_READ", None))

METRICS_REFRESH_INTERVAL_SECONDS = env.int("METRICS_REFRESH_INTERVAL_SECONDS", 60)

NODE_WEBSOCKET_URL = env.str("NODE_WEBSOCKET_URL", None)
# NODE_HTTPS_URL = env.str("NODE_HTTPS_URL", None)

METRICS_PORT = env.int("METRICS_PORT", 8000)

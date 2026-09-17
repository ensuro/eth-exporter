import os

# eth_exporter.config is read at import time (via environs) and chaindata builds an
# ArtifactLibrary from config.ABIS_PATH, which must be set before importing the package.
os.environ.setdefault("ABIS_PATH", os.path.join(os.path.dirname(__file__), "..", "samples", "abis"))

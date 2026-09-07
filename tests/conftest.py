import sys
from pathlib import Path

# the api service is not installed, it is run from its own directory, so tests
# need to be told where it lives
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))

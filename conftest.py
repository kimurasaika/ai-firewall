import sys
from pathlib import Path

# Ensure project root is always on sys.path regardless of how pytest is invoked
root = Path(__file__).parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

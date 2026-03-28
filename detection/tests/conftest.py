"""Pytest configuration and fixtures."""

import sys
from pathlib import Path

# Add parent directory to path so detection module can be imported
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

"""Shared test fixtures for Beast Mailbox Agent."""

import sys
from pathlib import Path

import pytest

# Ensure the source directory is importable without installing the package.
SRC_PATH = Path(__file__).resolve().parent.parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

# Fixtures will be added here as implementation progresses

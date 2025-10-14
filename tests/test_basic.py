"""Basic tests to verify setup."""

import beast_mailbox_agent


def test_version():
    """Test that version is defined."""
    assert hasattr(beast_mailbox_agent, "__version__")
    assert beast_mailbox_agent.__version__ == "0.1.0"


def test_import():
    """Test that package can be imported."""
    assert beast_mailbox_agent is not None


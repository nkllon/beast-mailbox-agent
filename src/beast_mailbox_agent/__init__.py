"""Beast Mailbox Agent - LLM agent that receives and responds to prompts via mailbox."""

from .config import AgentConfig, ConfigError  # noqa: F401
from .runtime import AgentRuntime  # noqa: F401

__all__ = ["AgentConfig", "AgentRuntime", "ConfigError", "__version__"]

__version__ = "0.1.0"

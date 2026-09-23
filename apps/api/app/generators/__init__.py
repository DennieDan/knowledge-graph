"""Generator package: importing it populates the registry."""
from . import conversations, files, stub  # noqa: F401
from .registry import (  # noqa: F401
    GENERATORS,
    GenerationContext,
    prompt_key_for,
    prompt_version,
    register,
)

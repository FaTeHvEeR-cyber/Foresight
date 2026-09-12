"""Memory management package for Foresight backend."""

from src.memory.lifecycle import EphemeralScope, ephemeral_processing

__all__ = ["ephemeral_processing", "EphemeralScope"]

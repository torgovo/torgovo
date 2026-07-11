"""
Trading managers module.

This module provides the execution layer that bridges Django models
with pure Python strategies and adapters.
"""
from .execution import BotExecutor, run_bot

__all__ = ['BotExecutor', 'run_bot']

"""
Agents module containing personal agent implementations.

This module provides:
- BasePersonalAgent: Base class with shared utilities
- EmbodiedAgent: Agent for robot/embodied tasks
- ShoppingAgent: Agent for shopping assistance tasks
"""

from agents.base import BasePersonalAgent
from agents.embodied_agent import EmbodiedAgent
from agents.shopping_agent import ShoppingAgent

__all__ = ["BasePersonalAgent", "EmbodiedAgent", "ShoppingAgent"]


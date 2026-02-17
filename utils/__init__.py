"""
Utilities module with shared helper functions.

This module provides:
- LLMClient: OpenAI API client for LLM generation
- JSON utilities for reading/writing data
- Agent utilities for metrics and memory initialization
"""

from utils.agent_utils import (
    calculate_acpe,
    compute_cfus,
    get_mc_dataset,
    get_metrics,
    get_option,
    initialize_memory_banks,
    process_mc_raw,
)
from utils.json_utils import append_to_json_list, read_json, write_json
from utils.llm import LLMClient

__all__ = [
    "LLMClient",
    "write_json",
    "read_json",
    "append_to_json_list",
    "get_option",
    "get_mc_dataset",
    "process_mc_raw",
    "initialize_memory_banks",
    "get_metrics",
    "compute_cfus",
    "calculate_acpe",
]


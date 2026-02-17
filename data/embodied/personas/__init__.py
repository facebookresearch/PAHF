"""
Embodied agent personas.

Contains persona prompts for:
- original_persona: Original user personas
- evolved_persona: Evolved user personas (with changed preferences)
"""

from data.embodied.personas.evolved_persona import prompt_evolved_dict
from data.embodied.personas.original_persona import prompt_dict

__all__ = ["prompt_dict", "prompt_evolved_dict"]


"""
Unified entry point for running PAHF (Personalized Agents from Human Feedback).

Usage:
    python run_agent.py --agent embodied
    python run_agent.py --agent shopping
"""

import argparse
import json
import os
import sys

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.embodied_agent import EmbodiedAgent
from agents.shopping_agent import ShoppingAgent
from utils.llm import LLMClient


def run_embodied_agent(
    enable_memory=True,
    mem_style="sql",
    learning_iter=3,
    model="gpt-4o",
):
    """Run the embodied agent for robot tasks.
    
    Args:
        enable_memory: If True, runs full PAHF with memory and feedback.
                      If False, runs baseline without memory.
        mem_style: Memory backend ('sql' or 'faiss')
        learning_iter: Number of learning iterations for phases 1 and 3
        model: LLM model to use
    """
    mode = "PAHF" if enable_memory else "Baseline (no memory)"
    print("\n" + "=" * 70)
    print("Running Embodied Agent (Robot Tasks)")
    print(f"Mode: {mode}, Memory: {mem_style if enable_memory else 'N/A'}")
    print("=" * 70 + "\n")

    # Import personas
    from data.embodied.personas.evolved_persona import prompt_evolved_dict
    from data.embodied.personas.original_persona import prompt_dict

    # Define phase data paths
    phase1 = "data/embodied/scenarios/original_scenarios_A.json"
    phase2 = "data/embodied/scenarios/original_scenarios_B.json"
    phase3 = "data/embodied/scenarios/evolved_scenarios_A.json"
    phase4 = "data/embodied/scenarios/evolved_scenarios_B.json"

    all_phases = [phase1, phase2, phase3, phase4]
    prompts = {"original": prompt_dict, "evolved": prompt_evolved_dict}

    # Create LLM client and agent
    llm_client = LLMClient(model=model)
    agent = EmbodiedAgent(llm_client)

    # Run full study
    # PAHF uses both pre-action and post-action feedback when memory is enabled
    agent.run_full_study(
        all_phases,
        prompts,
        enable_memory=enable_memory,
        mem_style=mem_style,
        learning_iter=learning_iter,
        enable_pre_feedback=enable_memory,  # Pre-action feedback enabled with memory
        enable_post_feedback=enable_memory,  # Post-action feedback enabled with memory
    )

    print("\n" + "=" * 70)
    print("Embodied Agent Study Complete!")
    print("=" * 70 + "\n")


def run_shopping_agent(
    enable_memory=True,
    mem_style="sql",
    learning_iter=3,
    model="gpt-4o",
    feedback_style="detailed",
):
    """Run the shopping agent for e-commerce tasks.
    
    Args:
        enable_memory: If True, runs full PAHF with memory and feedback.
                      If False, runs baseline without memory.
        mem_style: Memory backend ('sql' or 'faiss')
        learning_iter: Number of learning iterations for phases 1 and 3
        model: LLM model to use
    """
    mode = "PAHF" if enable_memory else "Baseline (no memory)"
    print("\n" + "=" * 70)
    print("Running Shopping Agent (E-commerce Tasks)")
    print(f"Mode: {mode}, Memory: {mem_style if enable_memory else 'N/A'}")
    print("=" * 70 + "\n")

    # Define phase data paths
    phase1 = "data/shopping/phase1.json"
    phase2 = "data/shopping/phase2.json"
    phase3 = "data/shopping/phase3.json"
    phase4 = "data/shopping/phase4.json"

    all_phases = [phase1, phase2, phase3, phase4]

    # Load persona dict from JSON
    persona_path = "data/shopping/original_persona.json"
    with open(persona_path, "r") as f:
        prompt_dict = json.load(f)

    # Load updated personas for Phase 3 & 4
    updated_persona_path = "data/shopping/updated_persona.json"
    with open(updated_persona_path, "r") as f:
        updated_prompt_dict = json.load(f)

    # Load persona_info for rule-based feedback
    persona_info_path = "data/shopping/persona_info.json"
    with open(persona_info_path, "r") as f:
        all_persona_info = json.load(f)

    # Extract just the persona_info part
    persona_info_dict = {
        name: data["persona_info"] for name, data in all_persona_info.items()
    }

    # Load updated persona_info for Phase 3 & 4
    updated_persona_info_path = "data/shopping/updated_persona_info.json"
    with open(updated_persona_info_path, "r") as f:
        all_updated_persona_info = json.load(f)

    # Extract just the persona_info part for Phase 3 & 4
    updated_persona_info_dict = {
        name: data["persona_info"] for name, data in all_updated_persona_info.items()
    }

    # Create LLM client and agent
    llm_client = LLMClient(model=model)
    agent = ShoppingAgent(llm_client)

    # Run full study
    # PAHF uses both pre-action and post-action feedback when memory is enabled
    agent.run_full_study(
        all_phases,
        prompt_dict,
        enable_memory=enable_memory,
        mem_style=mem_style,
        learning_iter=learning_iter,
        enable_pre_feedback=enable_memory,  # Pre-action feedback enabled with memory
        enable_post_feedback=enable_memory,  # Post-action feedback enabled with memory
        feedback_style=feedback_style,
        updated_prompts=updated_prompt_dict,
        persona_info_dict=persona_info_dict,
        updated_persona_info_dict=updated_persona_info_dict,
    )

    print("\n" + "=" * 70)
    print("Shopping Agent Study Complete!")
    print("=" * 70 + "\n")


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Run PAHF (Personalized Agents from Human Feedback)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run PAHF embodied agent with SQLite memory
  python run_agent.py --agent embodied

  # Run PAHF embodied agent with FAISS memory
  python run_agent.py --agent embodied --mem_style faiss

  # Run baseline (no memory) for comparison
  python run_agent.py --agent embodied --no-memory

  # Run with custom learning iterations
  python run_agent.py --agent embodied --learning_iter 5
        """,
    )

    parser.add_argument(
        "--agent",
        type=str,
        required=True,
        choices=["embodied", "shopping"],
        help="Which agent to run: 'embodied' for robot tasks, 'shopping' for e-commerce",
    )

    parser.add_argument(
        "--mem_style",
        type=str,
        default="sql",
        choices=["sql", "faiss"],
        help="Memory backend style (default: sql)",
    )

    parser.add_argument(
        "--no-memory",
        action="store_true",
        help="Run baseline without memory (disables PAHF feedback loop)",
    )

    parser.add_argument(
        "--learning_iter",
        type=int,
        default=3,
        help="Number of learning iterations for phases 1 and 3 (default: 3)",
    )

    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o",
        help="LLM model to use (default: gpt-4o)",
    )

    parser.add_argument(
        "--shopping_feedback_style",
        type=str,
        default="minimal",
        choices=["detailed", "minimal"],
        help="Shopping post-feedback style: 'detailed' (default) or 'minimal'",
    )

    args = parser.parse_args()

    # Run the selected agent
    if args.agent == "embodied":
        run_embodied_agent(
            enable_memory=not args.no_memory,
            mem_style=args.mem_style,
            learning_iter=args.learning_iter,
            model=args.model,
        )
    elif args.agent == "shopping":
        run_shopping_agent(
            enable_memory=not args.no_memory,
            mem_style=args.mem_style,
            learning_iter=args.learning_iter,
            model=args.model,
            feedback_style=args.shopping_feedback_style,
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

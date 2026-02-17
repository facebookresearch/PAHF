"""
Shared utility functions for embodied_agent.py and shopping_agent.py
Contains common functionality to reduce code duplication.
"""

import os

from memory.banks import DragonPlusEmbedding, FAISSMemoryBank, SQLiteMemoryBank


def get_option(gen, option):
    """Extract a specific option from generated text."""
    gen_split = gen.split("\n")
    for item in gen_split:
        if item.startswith(option):
            return item
    # Keep the placeholder with a marker to indicate it wasn't generated
    # This prevents incorrect mapping in letter_option dictionary
    return option


def get_mc_dataset(dataset, llm_client):
    """Generate multiple choice options using LLM."""
    num_data = len(dataset)
    for i in range(num_data):
        test_data = dataset[i]
        prompt = test_data["mc_gen_prompt"]

        gen = llm_client.generate(prompt)

        org = prompt.split("\n\n")[-2]
        org = org.replace("A)", get_option(gen, "A)"))
        org = org.replace("B)", get_option(gen, "B)"))
        org = org.replace("C)", get_option(gen, "C)"))
        org = org.replace("D)", get_option(gen, "D)"))

        test_data["mc_gen_raw"] = org
        dataset[i] = test_data

    return dataset


def process_mc_raw(mc_raw, add_mc="an option not listed here"):
    """Process raw multiple choice text into a list of options."""
    mc_all = mc_raw.split("\n")

    mc_processed_all = []
    for mc in mc_all:
        mc = mc.strip()
        option_list = ["A)", "B)", "C)", "D)"]

        # skip nonsense
        if len(mc) < 5 or mc[:2] not in option_list:
            continue
        if "both" in mc.split() or "all" in mc.split():
            continue
        mc = mc[2:]  # remove a), b), ...
        mc = mc.strip().split(".")[0]
        mc_processed_all.append(mc)
    return mc_processed_all


def initialize_memory_banks(
    prompts,
    mem_style,
    cur_dir,
    agent_type="embodied_agent",
    model=None,
    human_model=None,
):
    """Initialize memory banks for all people in prompts.

    Args:
        prompts: Dictionary with person names as keys
        mem_style: Either "sql" or "faiss"
        cur_dir: Base directory for memory storage
        agent_type: Type of agent (e.g., "embodied_sql_pahf")
        model: AI agent model name (e.g., "gpt-4")
        human_model: Human simulator model name (e.g., "gpt-4")

    Returns:
        Dictionary mapping person names to memory bank instances
    """
    all_names = prompts.keys()
    all_memories = {}

    # Create model-specific subdirectory if models are provided
    if model and human_model:
        mem_path = os.path.join(cur_dir, model, human_model, mem_style)
    else:
        # Fallback to old structure
        mem_path = os.path.join(cur_dir, mem_style)

    # Create a SHARED embedding model to avoid loading it multiple times
    # This is critical for performance - loading the model once instead of per-person
    print("Loading embedding model...")
    shared_embedding_model = DragonPlusEmbedding()
    print("Embedding model loaded.")

    if mem_style == "sql":
        # Use shared database for all people
        shared_db_path = os.path.join(mem_path, f"{agent_type}_memory.db")
        for name in all_names:
            specific_memory = SQLiteMemoryBank(
                db_path=shared_db_path,
                person_id=name,
                embedding_model=shared_embedding_model,
            )
            all_memories[name] = specific_memory
    else:
        # Use shared FAISS index for all people
        shared_faiss_path = os.path.join(mem_path, f"{agent_type}_memory")
        for name in all_names:
            specific_memory = FAISSMemoryBank(
                embedding_model=shared_embedding_model,
                use_dot_product=True,
                persistence_path=shared_faiss_path,
                person_id=name,
            )
            all_memories[name] = specific_memory

    return all_memories


def get_metrics(test_set):
    """Calculate evaluation metrics from test results.

    Returns:
        acc: Accuracy (0-1)
        ff: Feedback frequency (0-1) - proportion of samples with any feedback
    """
    correct_list = [item["correct"] for item in test_set]
    feedback_list = [item["feedback"] for item in test_set]

    acc = sum(correct_list) / len(correct_list)
    ff = sum(feedback_list) / len(feedback_list)

    return acc, ff


def compute_cfus(results):
    """
    Conditional Feedback Utility Score
    Measures if feedback actually improves outcomes
    """
    # Split tasks by whether feedback was used
    with_feedback = [r for r in results if r["feedback"] > 0]
    without_feedback = [r for r in results if r["feedback"] == 0]

    # Handle edge cases
    if len(with_feedback) == 0:
        # Agent never asked for feedback - check if it was justified
        success_rate_no_fb = (
            sum(r["correct"] for r in without_feedback) / len(without_feedback)
            if without_feedback
            else 0.0
        )

        # If success rate is high, it's fine to not ask for feedback
        # If success rate is low, it's overconfident behavior
        # Use success rate directly as the score (0-1 range)
        return {
            "cfus": success_rate_no_fb,
            "p_success_with_feedback": 0.0,
            "p_success_no_feedback": success_rate_no_fb,
            "n_with_feedback": 0,
            "n_without_feedback": len(without_feedback),
            "interpretation": (
                "Never asked feedback - good (high success)"
                if success_rate_no_fb >= 0.8
                else f"Never asked feedback - overconfident (only {success_rate_no_fb:.1%} success)"
            ),
        }

    if len(without_feedback) == 0:
        # Agent always asked for feedback - check success rate
        success_rate_with_fb = (
            sum(r["correct"] for r in with_feedback) / len(with_feedback)
            if with_feedback
            else 0.0
        )

        # Always asking for feedback is inefficient but not necessarily bad
        # Success rate still matters most - penalize slightly for inefficiency
        return {
            "cfus": success_rate_with_fb * 0.9,  # 10% penalty for always asking
            "p_success_with_feedback": success_rate_with_fb,
            "p_success_no_feedback": float("nan"),
            "n_with_feedback": len(with_feedback),
            "n_without_feedback": 0,
            "interpretation": (
                "Always asked feedback - slightly inefficient but good success"
                if success_rate_with_fb >= 0.8
                else f"Always asked feedback - inefficient with only {success_rate_with_fb:.1%} success"
            ),
        }

    # Compute success rates
    p_success_with_fb = sum(r["correct"] for r in with_feedback) / len(with_feedback)
    p_success_no_fb = sum(r["correct"] for r in without_feedback) / len(
        without_feedback
    )

    # Avoid division by zero
    if p_success_no_fb == 0:
        cfus = float("inf") if p_success_with_fb > 0 else 1.0
        interpretation = "Failed all tasks without feedback"
    else:
        cfus = p_success_with_fb / p_success_no_fb
        interpretation = (
            "Feedback helps" if cfus > 1 else "Feedback hurts or unnecessary"
        )

    return {
        "cfus": cfus,
        "p_success_with_feedback": p_success_with_fb,
        "p_success_no_feedback": p_success_no_fb,
        "n_with_feedback": len(with_feedback),
        "n_without_feedback": len(without_feedback),
        "interpretation": interpretation,
    }


def calculate_acpe(iteration_results):
    """Calculate Average Cumulative Personalization Error (ACPE) across iterations.

    For a given phase with T learning iterations, let PE_t ∈ [0,1] denote the
    personalization error rate (fraction of incorrect tasks) at iteration t.
    ACPE_t = (1/t) * Σ(s=1 to t) PE_s

    Args:
        iteration_results: List of test_set results from each iteration.
                          Each element is a test_set (list of task results with 'correct' field).

    Returns:
        acpe_values: List of ACPE values for each iteration t, where
                    acpe_values[t-1] contains ACPE_t (the average cumulative error up to iteration t).
                    Values are in [0, 1] range (can be interpreted as percentages).

    Example:
        If iteration_results = [test_set_1, test_set_2, test_set_3]:
        - PE_1 = error rate at iteration 1
        - PE_2 = error rate at iteration 2
        - PE_3 = error rate at iteration 3
        - ACPE_1 = PE_1
        - ACPE_2 = (PE_1 + PE_2) / 2
        - ACPE_3 = (PE_1 + PE_2 + PE_3) / 3
        Returns: [ACPE_1, ACPE_2, ACPE_3]
    """
    if not iteration_results:
        return []

    pe_values = []  # Personalization error for each iteration

    # Calculate PE_t for each iteration
    for test_set in iteration_results:
        correct_list = [item["correct"] for item in test_set]
        # Personalization error = 1 - accuracy
        error_rate = 1.0 - (sum(correct_list) / len(correct_list))
        pe_values.append(error_rate)

    acpe_values = []  # Average cumulative personalization error

    # Calculate ACPE_t for each iteration t
    for t in range(1, len(pe_values) + 1):
        # ACPE_t = (1/t) * Σ(s=1 to t) PE_s
        acpe_t = sum(pe_values[:t]) / t
        acpe_values.append(acpe_t)

    return acpe_values

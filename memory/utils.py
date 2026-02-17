"""
Memory-related utility functions for agents.
Contains functions for memory formatting, storage, and retrieval.
"""

from prompts.embodied_prompts import keyword_prompt, query_expansion_prompt_template


def format_enhanced_memory(summ_info, llm_client):
    """Format memory with keyword augmentation."""
    task_relevance_prompt = f"Memory: {summ_info}\n\n{keyword_prompt}"
    keywords = llm_client.generate(task_relevance_prompt).strip()
    return f"{summ_info} | KEYWORDS: {keywords}"


def store_augmented_memory(memory, summ_info, llm_client):
    """Store memory with keyword augmentation."""
    enhanced_memory = format_enhanced_memory(summ_info, llm_client)
    # Add to memory bank
    memory.add(enhanced_memory)
    return enhanced_memory


def update_augmented_memory(memory, mem_id, summ_info, llm_client):
    """Update existing memory with keyword augmentation."""
    enhanced_memory = format_enhanced_memory(summ_info, llm_client)
    # Add to memory bank
    memory.update_memory(mem_id, enhanced_memory)
    return enhanced_memory


def enhanced_memory_retrieval(memory, task, llm_client, top_k=5):
    """Retrieve memories using query expansion and keyword matching."""
    # Query expansion for natural task statements
    query_expansion_prompt = f"{task}\n\n{query_expansion_prompt_template}"

    expanded_queries = llm_client.generate(query_expansion_prompt).strip().split("\n")

    # Search with multiple context-aware queries against augmented memories
    all_results = []
    for query in expanded_queries[:4]:
        clean_query = query.strip("- ").strip()
        if clean_query:
            results = memory.search(clean_query, top_k=2)
            all_results.extend(results)

    # Remove duplicates and clean results
    unique_results = []
    seen_texts = set()
    for score, text in all_results:
        # Extract just the memory part (before KEYWORDS)
        clean_text = text.split(" | KEYWORDS:")[0] if " | KEYWORDS:" in text else text
        if clean_text not in seen_texts:
            unique_results.append((score, clean_text))
            seen_texts.add(clean_text)

    # Take top results and format for context
    top_results = sorted(unique_results, reverse=True)[:top_k]
    context = "\n".join([f"- {text}" for _, text in top_results])
    return context


def simple_memory_retrieval(memory, task, top_k=5):
    """Retrieve memories using direct search without query expansion."""
    if not memory:
        return ""

    # Direct search using the task
    results = memory.search(task, top_k=top_k)

    # Format results as context
    context_lines = []
    for score, text in results:
        # Clean text by removing augmentation keywords if present
        clean_text = text.split(" | KEYWORDS:")[0] if " | KEYWORDS:" in text else text
        context_lines.append(f"- {clean_text}")

    return "\n".join(context_lines)

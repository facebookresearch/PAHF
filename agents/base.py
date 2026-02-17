"""
Lightweight base agent class for shared utilities.

This class provides common helper methods that both embodied and shopping agents can use,
while allowing each to maintain their own implementation where they differ.
"""

from typing import Tuple

from memory.utils import simple_memory_retrieval, store_augmented_memory


class BasePersonalAgent:
    """Base class providing shared utilities for personal agent implementations.

    This is a lightweight base class that provides common helper methods without
    forcing a specific implementation structure. Each agent can use what it needs
    and override/extend what it doesn't.
    """

    def __init__(self, llm_client, prompt_summarize, prompt_question, qa_prompt):
        """Initialize the base agent with common prompts.

        Args:
            llm_client: LLM client instance for generation
            prompt_summarize: Prompt template for summarizing memory context
            prompt_question: Prompt template for generating questions
            qa_prompt: Prompt template for Q&A formatting
        """
        self.llm_client = llm_client
        self.prompt_summarize = prompt_summarize
        self.prompt_question = prompt_question
        self.qa_prompt = qa_prompt

    def get_agent_type(self) -> str:
        """Return the agent type name. Override in subclasses."""
        return "Agent"

    def retrieve_memory_context(
        self,
        memory,
        task_query: str,
        whole_scenario: str,
    ) -> str:
        """Retrieve and summarize memory context for a task.

        This is a shared helper that both agents can use.

        Args:
            memory: Memory bank instance
            task_query: Query for memory retrieval
            whole_scenario: Complete scenario text

        Returns:
            Formatted context string
        """
        if not memory:
            return ""

        context = simple_memory_retrieval(memory, task_query, top_k=10)

        prompt_final2 = (
            self.prompt_summarize
            + "\n\n"
            + whole_scenario
            + "\n\n"
            + "Context:\n"
            + context
        )
        text = self.llm_client.generate(prompt_final2)
        summary = text.split("Summary: ")[-1]

        return f"Context: {summary}"

    def handle_pre_feedback(
        self,
        action: str,
        whole_scenario: str,
        scenario: str,
        prompt_human: str,
        memory,
        name: str,
        aug_mem: bool = False,
        enable_pre_feedback: bool = True,
    ) -> Tuple[int, str, str]:
        """Handle the ask-human pre-feedback flow.

        This is a shared helper that both agents can use.

        Args:
            action: Current action
            whole_scenario: Complete scenario text
            scenario: Scenario text without options
            prompt_human: Human persona prompt
            memory: Memory bank instance
            name: User name
            aug_mem: Whether to use augmented memory
            enable_pre_feedback: Whether to actually provide human answer

        Returns:
            Tuple of (pre_feedback_flag, qa_text, updated_action)
        """
        if "Ask human" not in action:
            return 0, "", action

        # Generate question (always generate, even if feedback disabled)
        prompt_final2 = self.prompt_question + "\n\n" + whole_scenario
        text = self.llm_client.generate(prompt_final2)
        question = text.split("Question: ")[-1]

        inject_question = f"{self.get_agent_type()} Question: {question}"

        # If pre-feedback is disabled, return question but with clear "no answer" message
        if not enable_pre_feedback:
            # Agent asked question but gets explicit "no answer" signal
            no_answer_msg = "[No answer provided]"
            qa = self.qa_prompt.format(question, no_answer_msg)
            return 1, qa, "Ask human"

        # Get human answer (only if pre-feedback is enabled)
        messages = [
            {"role": "system", "content": prompt_human},
            {"role": "user", "content": scenario + "\n\n" + inject_question},
        ]

        human_a = self.llm_client.generate(messages, use_human_model=True)
        qa = self.qa_prompt.format(question, human_a)

        # Update memory (only if pre-feedback is enabled)
        if memory:
            summ = f"{qa}\n\nAccording to this Q&A, please summarize the personalized information of {name} in one brief sentence."
            summ_info = self.llm_client.generate(summ).strip()
            (
                store_augmented_memory(memory, summ_info, self.llm_client)
                if aug_mem
                else memory.add(summ_info)
            )

        return 1, qa, "Ask human"

    def extract_action(self, gen_text: str) -> str:
        """Extract action from generated text.

        This is a shared helper that both agents can use.

        Args:
            gen_text: Generated text

        Returns:
            Extracted action
        """
        action = gen_text.split("Action: ")[-1].split("\n")[0].strip()

        # Clean up if "Ask human" has extra text
        if "Ask human" in action:
            action = "Ask human"

        return action

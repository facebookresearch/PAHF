import json
import os
import pdb
import random
import sqlite3
import sys
import time

sys.path.append(".")

import faiss
import numpy as np
from tqdm import tqdm

from agents.base import BasePersonalAgent
from memory.banks import FAISSMemoryBank, SQLiteMemoryBank
from memory.utils import (
    enhanced_memory_retrieval,
    format_enhanced_memory,
    simple_memory_retrieval,
    store_augmented_memory,
    update_augmented_memory,
)
from prompts.shopping_prompts import (
    check_update_prompt,
    gt_prompt,
    integration_prompt,
    judge_prompt,
    keyword_prompt,
    mc_gen_prompt_template,
    opt_q,
    product_check_prompt,
    prompt_question,
    prompt_react,
    prompt_react_no_ask,
    prompt_summarize,
    qa_prompt,
    query_expansion_prompt_template,
    scenario_test_prompt,
    summ_prompt_template,
    update_prompt_template,
)
from utils.agent_utils import (
    calculate_acpe,
    get_mc_dataset,
    get_metrics,
    get_option,
    initialize_memory_banks,
    process_mc_raw,
)
from utils.json_utils import write_json
from utils.llm import LLMClient


class ShoppingAgent(BasePersonalAgent):
    """Agent for shopping assistance tasks."""

    def __init__(self, llm_client):
        """Initialize the shopping agent.

        Args:
            llm_client: LLM client instance for generation
        """
        super().__init__(
            llm_client=llm_client,
            prompt_summarize=prompt_summarize,
            prompt_question=prompt_question,
            qa_prompt=qa_prompt,
        )

    def _is_option_acceptable(self, option_features, persona_prefs):
        """Check if all features in an option are acceptable (like_most or like_second).

        Args:
            option_features: List of feature values in the option
            persona_prefs: Dictionary of preferences for the product

        Returns:
            bool: True if all features are acceptable, False otherwise
        """
        for feature in option_features:
            is_acceptable = False
            for feat_category, prefs in persona_prefs.items():
                if feature == prefs.get("like_most"):
                    is_acceptable = True
                    break
                if feature in prefs.get("like_second", []):
                    is_acceptable = True
                    break
            if not is_acceptable:
                return False
        return True

    def _get_preferred_feature_in_gt(self, gt_option_features, chosen_option_features, persona_prefs):
        """Find a 'like_most' feature in GT that the chosen option doesn't have.

        Args:
            gt_option_features: List of feature values in the ground truth option
            chosen_option_features: List of feature values in the chosen option
            persona_prefs: Dictionary of preferences for the product

        Returns:
            str or None: A preferred feature from GT that differs from chosen option
        """
        for feature in gt_option_features:
            for feat_category, prefs in persona_prefs.items():
                if feature == prefs.get("like_most"):
                    # Check if the chosen option has the same feature category but different value
                    for chosen_feat in chosen_option_features:
                        # If chosen option has a different value for this category
                        if chosen_feat in prefs.get("like_second", []):
                            return feature
        return None

    def _wrong_option_feedback(self, action, gt_value, mc_gen_raw, option_features, prefs, feedback_style):
        """Generate feedback when the agent chose a wrong product option.

        Checks for disliked features first, then whether the option is acceptable but not best.
        """
        # Find disliked features
        disliked_features = []
        for feature_value in option_features:
            for feat_category, pref in prefs.items():
                if feature_value in pref.get("dislike", []):
                    disliked_features.append(feature_value)
                    break

        if disliked_features:
            return f"Option {action} won't work for me because I don't want {disliked_features[0]}."

        # No disliked features — check if option is acceptable (all features liked)
        if self._is_option_acceptable(option_features, prefs):
            if feedback_style == "minimal":
                if gt_value and gt_value in ["A", "B", "C"]:
                    return f"Option {action} meets my needs but I like Option {gt_value} more."
                else:
                    return f"Option {action} meets my needs."
            else:
                # Detailed: explain why GT is better
                if gt_value and gt_value in ["A", "B", "C"]:
                    gt_option_text = mc_gen_raw.split(f"{gt_value})")[1].split("\n")[0].strip()
                    gt_option_features = gt_option_text.split("with ")[1].split(" and ")
                    preferred_feature = self._get_preferred_feature_in_gt(
                        gt_option_features, option_features, prefs
                    )
                    if preferred_feature:
                        return f"Option {action} is okay, but I'd prefer Option {gt_value} because it has {preferred_feature} which I like more."
                    else:
                        return f"Option {action} works, but Option {gt_value} would be even better for me."
                else:
                    return f"Option {action} is acceptable."

        return f"Option {action} doesn't meet my needs."

    def _generate_post_feedback(self, action, test_data, name,
                                persona_info_dict, old_persona_info_dict, feedback_style):
        """Generate rule-based post-action feedback.

        Returns:
            str: Feedback message (empty string if action is unexpected).
        """
        gt_value = test_data.get("gt")

        # Correct choice (including gt=None → D is correct)
        if action == gt_value or (action == "D" and gt_value is None):
            return random.choice(["Right!", "Thanks!", "Perfect!", "That works!"])

        # Agent chose D but there was a correct option
        if action == "D" and gt_value is not None:
            return f"Option {gt_value} would have worked for me."

        # Agent chose a wrong product option (A/B/C)
        if action in ["A", "B", "C"]:
            mc_gen_raw = test_data.get("mc_gen_raw")
            option = mc_gen_raw.split(f"{action})")[1].split("\n")[0].strip()
            option_features = option.split("with ")[1].split(" and ")

            if (
                old_persona_info_dict
                and name in old_persona_info_dict
                and persona_info_dict
                and name in persona_info_dict
            ):
                # Phase 3/4: check for preference change
                old_prefs = old_persona_info_dict[name].get(test_data["product"], {})
                new_prefs = persona_info_dict[name].get(test_data["product"], {})

                # Was the option acceptable under old preferences?
                was_acceptable_old = True
                for feature_value in option_features:
                    for feat_category, prefs in old_prefs.items():
                        if feature_value in prefs.get("dislike", []):
                            was_acceptable_old = False
                            break
                    if not was_acceptable_old:
                        break

                # Is any feature now disliked that was previously liked?
                preference_changed = False
                changed_feature = None
                for feature_value in option_features:
                    is_disliked_new = False
                    for feat_category, prefs in new_prefs.items():
                        if feature_value in prefs.get("dislike", []):
                            if feature_value == old_prefs[feat_category].get(
                                "like_most"
                            ) or feature_value in old_prefs[feat_category].get(
                                "like_second", []
                            ):
                                preference_changed = True
                                changed_feature = feature_value
                                is_disliked_new = True
                                break
                    if is_disliked_new:
                        break

                if was_acceptable_old and preference_changed and changed_feature:
                    return (
                        f"Actually, my preferences have changed. "
                        f"I used to like {changed_feature}, but now I don't want it anymore."
                    )

                if not was_acceptable_old or not preference_changed:
                    return self._wrong_option_feedback(
                        action, gt_value, mc_gen_raw, option_features, new_prefs, feedback_style
                    )

            elif persona_info_dict and name in persona_info_dict:
                # Phase 1/2: standard wrong-option feedback
                persona_prefs = persona_info_dict[name].get(test_data["product"], {})
                return self._wrong_option_feedback(
                    action, gt_value, mc_gen_raw, option_features, persona_prefs, feedback_style
                )

            else:
                # No persona info available
                return f"Option {action} doesn't work for me."

        return ""

    def _process_feedback_into_memory(self, feedback, whole_scenario, name, memory, aug_mem):
        """Check whether feedback contains new preference info and store it in memory.

        Returns:
            int: 1 if memory was updated, 0 otherwise.
        """
        feedback_prompt = (
            f"{whole_scenario}\n\nHuman feedback: {feedback}\n\n"
            "Does this feedback reveal NEW preference information about product features "
            "(not just agreement/disagreement with the agent's action)? Only answer 'Yes' "
            "if it states a specific preference, like, dislike, or constraint. Simple "
            "confirmations like 'right', 'correct', 'yes', 'none work' should be 'No'. "
            "Answer 'Yes' or 'No'."
        )
        check = self.llm_client.generate(feedback_prompt)
        if "Yes" not in check and "yes" not in check:
            return 0

        # Summarize the feedback
        summ_prompt = (
            f"{whole_scenario}\n\nHuman feedback: {feedback}\n\n"
            f"{summ_prompt_template.format(name=name)}"
        )
        summ_info = self.llm_client.generate(summ_prompt)

        # Search for similar existing memory
        mem_id = memory.find_similar_memory(summ_info)

        if mem_id is not None:
            existing_memory = memory.get_memory(mem_id)
            product_check_prompt_new = product_check_prompt.format(
                existing_memory=summ_info, summ_info=existing_memory
            )
            product_match = self.llm_client.generate(product_check_prompt_new).strip()

            if "Yes" in product_match or "yes" in product_match:
                # Same product — merge the memories
                merge_prompt = integration_prompt.format(
                    existing_memory=existing_memory, summ_info=summ_info
                )
                merged_summary = self.llm_client.generate(merge_prompt).strip()
                if aug_mem:
                    update_augmented_memory(memory, mem_id, merged_summary, self.llm_client)
                else:
                    memory.update_memory(mem_id, merged_summary)
            else:
                # Different product — add as new memory
                if aug_mem:
                    store_augmented_memory(memory, summ_info, self.llm_client)
                else:
                    memory.add(summ_info)
        else:
            # No similar memory found — add as new
            if aug_mem:
                store_augmented_memory(memory, summ_info, self.llm_client)
            else:
                memory.add(summ_info)

        return 1

    def get_agent_type(self) -> str:
        """Return the agent type name."""
        return "Shopping Agent"

    def get_gt(self, test_data, whole_scenario):
        """Get ground truth for a test case."""
        name = whole_scenario.split("\n")[0].split(": ")[0]
        product_type = test_data["product"]

        # Get ground truth from test_data
        gt_value = test_data.get("gt")

        if gt_value is None:
            # None of the options satisfy, so correct answer is D
            return "D"
        else:
            # One of A, B, C satisfies
            return gt_value

    def get_test_predictions(
        self,
        test_set,
        all_memories,
        prompt_dict,
        persona_info_dict=None,
        old_persona_info_dict=None,
        enable_pre_feedback=True,
        enable_post_feedback=True,
        enable_memory=True,
        keep_whole_memory=True,
        aug_mem=False,
        feedback_style="detailed",
    ):
        """Get predictions for test set with memory and feedback."""
        num_test_data = len(test_set)

        for i in tqdm(range(num_test_data), desc="Processing tasks"):
            test_data = test_set[i]

            whole_scenario = test_data["mc_gen_raw"].strip()
            scenario = whole_scenario.split("Options:")[0].strip()

            # Extract user name and task
            name = scenario.split(": ")[0]
            task = scenario.split(": ")[1]

            mc_gen_all = process_mc_raw(whole_scenario, add_mc="Do not buy anything")

            # Get the human persona
            prompt_human = prompt_dict[name]
            memory = all_memories[name]

            letters = ["A", "B", "C", "D"]
            letter_option = {}
            for j in range(len(mc_gen_all)):
                try:
                    letter_option[letters[j]] = mc_gen_all[j]
                except:
                    pdb.set_trace()

            gt_option = self.get_gt(test_data, whole_scenario)

            # planning - use prompt based on pre_feedback setting
            if enable_pre_feedback:
                prompt_final = prompt_react + "\n\n" + whole_scenario
            else:
                prompt_final = prompt_react_no_ask + "\n\n" + whole_scenario
            pre_feedback = 0

            # Search memory (only if memory is enabled)
            if enable_memory and memory:
                # get context
                task_query = whole_scenario
                context_str = self.retrieve_memory_context(
                    memory, task_query, whole_scenario
                )
                if context_str:
                    prompt_final += "\n\n" + context_str

            gen_text = self.llm_client.generate(prompt_final).strip()
            action = self.extract_action(gen_text)

            # Clean up the gen_text if LLM accidentally generated a question after "Action: Ask human"
            if "Ask human" in action:
                # Find where "Action: Ask human" appears in gen_text
                action_idx = gen_text.find("Action: Ask human")
                if action_idx != -1:
                    # Cut off everything after "Action: Ask human"
                    gen_text = gen_text[: action_idx + len("Action: Ask human")]
                action = "Ask human"

            prompt_final += "\n\n" + gen_text

            # Ask human if required
            if "Ask human" in action:
                pre_feedback, qa, action = self.handle_pre_feedback(
                    action,
                    whole_scenario,
                    scenario,
                    prompt_human,
                    memory,
                    name,
                    aug_mem,
                    enable_pre_feedback,
                )
                if qa:
                    prompt_final += "\n\n" + qa
                    gen_text = self.llm_client.generate(prompt_final).strip()
                    action = self.extract_action(gen_text)
                    prompt_final += "\n\n" + gen_text

            # Post-action feedback (rule-based)
            feedback = ""
            if enable_post_feedback:
                feedback = self._generate_post_feedback(
                    action, test_data, name,
                    persona_info_dict, old_persona_info_dict, feedback_style,
                    )

            whole_prompt = prompt_final.strip() + (
                f"\n\n" + f"Human: {feedback}" if feedback else ""
            )

            # Incorporate feedback into memory
            post_feedback_occurred = 0
            if enable_post_feedback and enable_memory and memory and feedback:
                post_feedback_occurred = self._process_feedback_into_memory(
                    feedback, whole_scenario, name, memory, aug_mem
                        )

            # feedback
            test_data["post_feedback"] = post_feedback_occurred
            test_data["pre_feedback"] = pre_feedback
            test_data["feedback"] = (
                test_data["post_feedback"] or test_data["pre_feedback"]
            )

            # evaluate if the action is correct
            test_data["correct"] = 1 if action == gt_option else 0
            # get the ground truth option
            test_data["gt_option"] = gt_option
            # Get the llm predictions
            test_data["action"] = action

            test_data["whole_prompt"] = whole_prompt
            test_data["human_feedback"] = feedback
            test_data["memory_enabled"] = enable_memory

        return test_set, all_memories

    def load_shopping_data(self, json_path):
        """Load shopping data from JSON file."""
        with open(json_path, "r") as f:
            shopping_data = json.load(f)

        test_set = []
        for item in shopping_data:
            # Format: User: Task
            user = item["User"]
            task = item["Task"]
            product = item["product"]

            # Create scenario text
            scenario_text = f"{user}: {task}"

            # Create options text
            option_a = f"A) {product} with {' and '.join(item['Option A'])}"
            option_b = f"B) {product} with {' and '.join(item['Option B'])}"
            option_c = f"C) {product} with {' and '.join(item['Option C'])}"
            option_d = "D) Do not buy anything"

            options_text = f"Options:\n{option_a}\n{option_b}\n{option_c}\n{option_d}"

            # Create mc_gen_prompt (for potential option generation)
            mc_gen_prompt = (
                mc_gen_prompt_template.strip()
                + "\n\n"
                + scenario_text
                + "\n"
                + options_text
            )

            # Create mc_gen_raw (the formatted scenario with options)
            mc_gen_raw = scenario_text + "\n" + options_text

            test_set.append(
                {
                    "product": product,
                    "user": user,
                    "task": task,
                    "gt": item.get("gt"),
                    "mc_gen_prompt": mc_gen_prompt,
                    "mc_gen_raw": mc_gen_raw,
                }
            )

        return test_set

    def run_exp(
        self,
        data_path,
        all_memories,
        prompt_dict,
        persona_info_dict=None,
        old_persona_info_dict=None,
        enable_memory=True,
        enable_pre_feedback=True,
        enable_post_feedback=True,
        feedback_style="detailed",
    ):
        """Run experiment on data."""
        cur_dir = "."
        sys.path.append(cur_dir)

        # Load shopping data from JSON
        test_set = self.load_shopping_data(data_path)

        test_set, memory = self.get_test_predictions(
            test_set,
            prompt_dict=prompt_dict,
            all_memories=all_memories,
            persona_info_dict=persona_info_dict,
            old_persona_info_dict=old_persona_info_dict,
            enable_memory=enable_memory,
            enable_pre_feedback=enable_pre_feedback,
            enable_post_feedback=enable_post_feedback,
            feedback_style=feedback_style,
        )

        return test_set, memory

    def run_study(
        self,
        data_path,
        prompts,
        enable_memory=True,
        mem_style="sql",
        all_memories=None,
        persona_info_dict=None,
        old_persona_info_dict=None,
        phase_idx=1,
        enable_pre_feedback=True,
        enable_post_feedback=True,
        feedback_style="detailed",
        db_path="memory/test_memory.db",
    ):
        """Run a study phase."""
        cur_dir = "./memory"
        sys.path.append(cur_dir)

        # PAHF uses both pre-action and post-action feedback with memory
        aug_text = "pahf" if enable_memory else "base"

        if all_memories is None:
            all_memories = initialize_memory_banks(
                prompts, mem_style, cur_dir, f"shopping_agent_{aug_text}"
            )

        test_set, all_memories = self.run_exp(
            data_path,
            all_memories=all_memories,
            prompt_dict=prompts,
            persona_info_dict=persona_info_dict,
            old_persona_info_dict=old_persona_info_dict,
            enable_memory=enable_memory,
            enable_pre_feedback=enable_pre_feedback,
            enable_post_feedback=enable_post_feedback,
            feedback_style=feedback_style,
        )

        return test_set, all_memories

    def run_full_study(
        self,
        all_phases,
        prompts,
        enable_memory=True,
        mem_style="sql",
        learning_iter=3,
        enable_pre_feedback=True,
        enable_post_feedback=True,
        feedback_style="detailed",
        updated_prompts=None,
        persona_info_dict=None,
        updated_persona_info_dict=None,
    ):
        """Run full study with multiple phases.

        Args:
            all_phases: List of phase data paths [phase1, phase2, phase3, phase4]
            prompts: Dictionary of prompts for phases 1 & 2
            enable_memory: Whether to use memory
            mem_style: Memory style ('sql' or 'faiss')
            learning_iter: Number of learning iterations for phases 1 and 3
            enable_pre_feedback: Enable pre-action feedback for phases 1 and 3
            enable_post_feedback: Enable post-action feedback for phases 1 and 3
            feedback_style: Post-action feedback style ('detailed' or 'minimal')
            updated_prompts: Dictionary of prompts for phases 3 & 4 (optional)
            persona_info_dict: Persona info for phases 1 & 2 (optional)
            updated_persona_info_dict: Updated persona info for phases 3 & 4 (optional)
        """
        cur_dir = "."
        sys.path.append(cur_dir)

        # Unpack phases
        phase1 = all_phases[0] if len(all_phases) > 0 else None
        phase2 = all_phases[1] if len(all_phases) > 1 else None
        phase3 = all_phases[2] if len(all_phases) > 2 else None
        phase4 = all_phases[3] if len(all_phases) > 3 else None

        if not enable_memory:
            learning_iter = 1

        memory = None

        # PAHF uses both pre-action and post-action feedback with memory
        aug_text = "pahf" if enable_memory else "base"

        # Phase 1: Training with feedback (based on flags)
        phase1_results = []
        if phase1 is not None:
            for i in range(learning_iter):
                test_set, memory = self.run_study(
                    phase1,
                    prompts,
                    enable_memory=enable_memory,
                    mem_style=mem_style,
                    all_memories=memory,
                    persona_info_dict=persona_info_dict,
                    phase_idx=1,
                    enable_pre_feedback=enable_pre_feedback,
                    enable_post_feedback=enable_post_feedback,
                    feedback_style=feedback_style,
                )
                phase1_results.append(test_set)
                acc, ff = get_metrics(test_set)
                # Calculate ACPE up to current iteration
                acpe_values = calculate_acpe(phase1_results)
                current_acpe = acpe_values[-1] if acpe_values else 0
                write_json(
                    test_set,
                    os.path.join(
                        cur_dir,
                        f"output/shopping/{mem_style}/{aug_text}/phase1_iter_{i+1}.json",
                    ),
                )
                print(f"Phase 1 iter {i+1}: acc={acc:.3f}, ff={ff:.3f}, ACPE={current_acpe:.3f}")

        # Phase 2: Evaluation only (NO feedback)
        test_set, memory = self.run_study(
            phase2,
            prompts,
            enable_memory=enable_memory,
            mem_style=mem_style,
            all_memories=memory,
            persona_info_dict=persona_info_dict,
            phase_idx=2,
            enable_pre_feedback=False,  # No feedback in test phase
            enable_post_feedback=False,  # No feedback in test phase
            feedback_style=feedback_style,
        )
        acc, ff = get_metrics(test_set)
        write_json(
            test_set,
            os.path.join(
                cur_dir, f"output/shopping/{mem_style}/{aug_text}/phase2.json"
            ),
        )

        print(f"Phase 2: acc={acc:.3f}, ff={ff:.3f}")

        # Phase 3: Training with feedback (based on flags)
        phase3_results = []
        if phase3 is not None and updated_prompts is not None:
            print("\n" + "=" * 70)
            print("Starting Phase 3 training with updated personas...")
            print("=" * 70)

            # Use updated_persona_info_dict for Phase 3 if provided, otherwise fallback to original
            phase3_persona_info = (
                updated_persona_info_dict
                if updated_persona_info_dict
                else persona_info_dict
            )

            for i in range(learning_iter):
                test_set, memory = self.run_study(
                    phase3,
                    updated_prompts,
                    enable_memory=enable_memory,
                    mem_style=mem_style,
                    all_memories=memory,
                    persona_info_dict=phase3_persona_info,
                    old_persona_info_dict=persona_info_dict,  # Pass original preferences as "old"
                    phase_idx=3,
                    enable_pre_feedback=enable_pre_feedback,
                    enable_post_feedback=enable_post_feedback,
                    feedback_style=feedback_style,
                )
                phase3_results.append(test_set)
                acc, ff = get_metrics(test_set)
                # Calculate ACPE up to current iteration
                acpe_values = calculate_acpe(phase3_results)
                current_acpe = acpe_values[-1] if acpe_values else 0
                write_json(
                    test_set,
                    os.path.join(
                        cur_dir,
                        f"output/shopping/{mem_style}/{aug_text}/phase3_iter_{i+1}.json",
                    ),
                )

                print(f"Phase 3 iter {i+1}: acc={acc:.3f}, ff={ff:.3f}, ACPE={current_acpe:.3f}")

        # Phase 4: Evaluation only (NO feedback)
        if phase4 is not None and updated_prompts is not None:
            print("\n" + "=" * 70)
            print("Starting Phase 4 evaluation with updated personas...")
            print("=" * 70)

            # Use updated_persona_info_dict for Phase 4 if provided, otherwise fallback to original
            phase4_persona_info = (
                updated_persona_info_dict
                if updated_persona_info_dict
                else persona_info_dict
            )

            test_set, memory = self.run_study(
                phase4,
                updated_prompts,
                enable_memory=enable_memory,
                mem_style=mem_style,
                all_memories=memory,
                persona_info_dict=phase4_persona_info,
                old_persona_info_dict=persona_info_dict,  # Pass original preferences as "old"
                phase_idx=4,
                enable_pre_feedback=False,  # No feedback in test phase
                enable_post_feedback=False,  # No feedback in test phase
                feedback_style=feedback_style,
            )
            acc, ff = get_metrics(test_set)
            write_json(
                test_set,
                os.path.join(
                    cur_dir, f"output/shopping/{mem_style}/{aug_text}/phase4.json"
                ),
            )

            print(f"Phase 4: acc={acc:.3f}, ff={ff:.3f}")

    def run_phase1_phase2(
        self,
        phase1,
        phase2,
        prompts,
        enable_memory=True,
        mem_style="sql",
        learning_iter=3,
        enable_pre_feedback=True,
        enable_post_feedback=True,
        feedback_style="detailed",
        persona_info_dict=None,
        memory_save_path=None,
    ):
        """Run Phase 1 and Phase 2, save memory for later use.

        Args:
            phase1: Path to phase 1 data
            phase2: Path to phase 2 data
            prompts: Dictionary of prompts for phases 1 & 2
            enable_memory: Whether to use memory
            mem_style: Memory style ('sql' or 'faiss')
            learning_iter: Number of learning iterations for phase 1
            enable_pre_feedback: Enable pre-action feedback for phase 1
            enable_post_feedback: Enable post-action feedback for phase 1
            feedback_style: Post-action feedback style ('detailed' or 'minimal')
            persona_info_dict: Persona info for phases 1 & 2
            memory_save_path: Path to save memory (if None, uses default)
        """
        cur_dir = "."
        sys.path.append(cur_dir)

        if not enable_memory:
            learning_iter = 1

        memory = None

        # PAHF uses both pre-action and post-action feedback with memory
        aug_text = "pahf" if enable_memory else "base"

        # Initialize memory banks with memory2/ directory
        if enable_memory:
            from agent_utils import initialize_memory_banks

            memory_dir = os.path.join(cur_dir, "memory2")
            # Get model names from self.llm_client
            agent_model = (
                self.llm_client.model if hasattr(self.llm_client, "model") else None
            )
            human_sim_model = (
                self.llm_client.human_model
                if hasattr(self.llm_client, "human_model")
                else None
            )
            memory = initialize_memory_banks(
                prompts,
                mem_style,
                memory_dir,
                f"shopping_{mem_style}_{aug_text}",
                model=agent_model,
                human_model=human_sim_model,
            )

        # Phase 1: Training with feedback
        print("\n" + "=" * 70)
        print("Starting Phase 1 training...")
        print("=" * 70)

        # Get model names for output directory
        agent_model = (
            self.llm_client.model if hasattr(self.llm_client, "model") else None
        )
        human_sim_model = (
            self.llm_client.human_model
            if hasattr(self.llm_client, "human_model")
            else None
        )

        # Construct output directory with model info
        if agent_model and human_sim_model:
            output_base = f"output2/shopping/{agent_model}/{human_sim_model}/{mem_style}/{aug_text}"
        else:
            output_base = f"output2/shopping/{mem_style}/{aug_text}"

        phase1_results = []
        for i in range(learning_iter):
            test_set, memory = self.run_study(
                phase1,
                prompts,
                enable_memory=enable_memory,
                mem_style=mem_style,
                all_memories=memory,
                persona_info_dict=persona_info_dict,
                phase_idx=1,
                enable_pre_feedback=enable_pre_feedback,
                enable_post_feedback=enable_post_feedback,
                feedback_style=feedback_style,
            )
            phase1_results.append(test_set)
            acc, ff = get_metrics(test_set)
            # Calculate ACPE up to current iteration
            acpe_values = calculate_acpe(phase1_results)
            current_acpe = acpe_values[-1] if acpe_values else 0
            write_json(
                test_set,
                os.path.join(
                    cur_dir,
                    f"{output_base}/phase1_iter_{i+1}.json",
                ),
            )
            print(f"Phase 1 iter {i+1}: acc={acc:.3f}, ff={ff:.3f}, ACPE={current_acpe:.3f}")

        # Phase 2: Evaluation only (NO feedback)
        print("\n" + "=" * 70)
        print("Starting Phase 2 evaluation...")
        print("=" * 70)

        test_set, memory = self.run_study(
            phase2,
            prompts,
            enable_memory=enable_memory,
            mem_style=mem_style,
            all_memories=memory,
            persona_info_dict=persona_info_dict,
            phase_idx=2,
            enable_pre_feedback=False,
            enable_post_feedback=False,
            feedback_style=feedback_style,
        )
        acc, ff = get_metrics(test_set)
        write_json(
            test_set,
            os.path.join(cur_dir, f"{output_base}/phase2.json"),
        )

        print(f"Phase 2: acc={acc:.3f}, ff={ff:.3f}")

        # Save memory for phase 3-4
        if enable_memory and memory:
            if memory_save_path is None:
                memory_save_path = os.path.join(
                    cur_dir,
                    f"memory_checkpoints2/shopping/{mem_style}/{aug_text}/phase1_2_memory",
                )

            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(memory_save_path), exist_ok=True)

            if mem_style == "faiss":
                # Save FAISS index for all personas
                for person_id in memory.keys():
                    person_memory = memory[person_id]
                    person_save_path = f"{memory_save_path}_{person_id}"
                    person_memory.save_index(person_save_path)
                    print(f"Saved FAISS memory for {person_id} to {person_save_path}")
            else:
                # For SQL, the database file is already persisted in memory2/
                # Just print the db_path for reference
                sample_person = list(memory.keys())[0]
                db_path = memory[sample_person].db_path
                print(f"SQLite memory persisted at: {db_path}")

        print("\n" + "=" * 70)
        print("Phase 1-2 Complete! Memory saved for Phase 3-4.")
        print("=" * 70)

        return memory

    def run_phase3_phase4(
        self,
        phase3,
        phase4,
        updated_prompts,
        enable_memory=True,
        mem_style="sql",
        learning_iter=3,
        enable_pre_feedback=True,
        enable_post_feedback=True,
        feedback_style="detailed",
        persona_info_dict=None,
        updated_persona_info_dict=None,
        memory_load_path=None,
        db_path=None,
    ):
        """Load memory from Phase 1-2 and run Phase 3 and Phase 4.

        Args:
            phase3: Path to phase 3 data
            phase4: Path to phase 4 data
            updated_prompts: Dictionary of prompts for phases 3 & 4
            enable_memory: Whether to use memory
            mem_style: Memory style ('sql' or 'faiss')
            learning_iter: Number of learning iterations for phase 3
            enable_pre_feedback: Enable pre-action feedback for phase 3
            enable_post_feedback: Enable post-action feedback for phase 3
            feedback_style: Post-action feedback style ('detailed' or 'minimal')
            persona_info_dict: Original persona info (for reference)
            updated_persona_info_dict: Updated persona info for phases 3 & 4
            memory_load_path: Path to load memory from (if None, uses default)
            db_path: Path to SQLite database (only used for SQL memory style)
        """
        cur_dir = "."
        sys.path.append(cur_dir)

        if not enable_memory:
            learning_iter = 1

        # PAHF uses both pre-action and post-action feedback with memory
        aug_text = "pahf" if enable_memory else "base"

        # Get model names from self.llm_client (needed for output directory even without memory)
        agent_model = (
            self.llm_client.model if hasattr(self.llm_client, "model") else None
        )
        human_sim_model = (
            self.llm_client.human_model
            if hasattr(self.llm_client, "human_model")
            else None
        )

        # Load memory from phase 1-2
        memory = None
        if enable_memory:

            if mem_style == "faiss":
                # Load FAISS memory from memory2/ (where auto-save writes during Phase 1-2)
                if memory_load_path is None:
                    # Construct path with model subdirectories if models are provided
                    if agent_model and human_sim_model:
                        memory_load_path = os.path.join(
                            cur_dir,
                            f"memory2/{agent_model}/{human_sim_model}/{mem_style}/shopping_{mem_style}_{aug_text}",
                        )
                    else:
                        # Fallback to old structure
                        memory_load_path = os.path.join(
                            cur_dir,
                            f"memory2/{mem_style}/shopping_{mem_style}_{aug_text}",
                        )

                # Get person IDs from updated_prompts (which is a dict with person names as keys)
                memory = {}
                for person_id in updated_prompts.keys():
                    person_load_path = f"{memory_load_path}_{person_id}"
                    if os.path.exists(f"{person_load_path}.index"):
                        from memory import FAISSMemoryBank

                        # Create with persistence_path for auto-save
                        person_memory = FAISSMemoryBank(
                            person_id=person_id,
                            persistence_path=memory_load_path,
                        )
                        person_memory.load_index(person_load_path)
                        memory[person_id] = person_memory
                        print(
                            f"Loaded FAISS memory for {person_id} from {person_load_path}"
                        )
                        print(
                            f"  Auto-save enabled to: {memory_load_path}_{person_id}.*"
                        )
                    else:
                        print(
                            f"Warning: No saved memory found for {person_id}, starting fresh"
                        )
                        from memory import FAISSMemoryBank

                        memory[person_id] = FAISSMemoryBank(
                            person_id=person_id,
                            persistence_path=memory_load_path,
                        )
            else:
                # Load SQL memory from memory2/ - just reconnect to the same database
                if db_path is None:
                    # Construct path with model subdirectories if models are provided
                    if agent_model and human_sim_model:
                        db_path = os.path.join(
                            cur_dir,
                            f"memory2/{agent_model}/{human_sim_model}/{mem_style}/shopping_{mem_style}_{aug_text}_memory.db",
                        )
                    else:
                        # Fallback to old structure
                        db_path = os.path.join(
                            cur_dir,
                            f"memory2/{mem_style}/shopping_{mem_style}_{aug_text}_memory.db",
                        )

                # Get person IDs from updated_prompts (which is a dict with person names as keys)
                memory = {}
                from memory import SQLiteMemoryBank

                for person_id in updated_prompts.keys():
                    memory[person_id] = SQLiteMemoryBank(
                        db_path=db_path, person_id=person_id
                    )
                print(f"Loaded SQLite memory from: {db_path}")

        # Use updated_persona_info_dict for Phase 3 if provided
        phase3_persona_info = (
            updated_persona_info_dict
            if updated_persona_info_dict
            else persona_info_dict
        )

        # Construct output directory with model info
        if agent_model and human_sim_model:
            output_base = f"output2/shopping/{agent_model}/{human_sim_model}/{mem_style}/{aug_text}"
        else:
            output_base = f"output2/shopping/{mem_style}/{aug_text}"

        # Phase 3: Training with feedback
        print("\n" + "=" * 70)
        print("Starting Phase 3 training with updated personas...")
        print("=" * 70)

        phase3_results = []
        for i in range(learning_iter):
            test_set, memory = self.run_study(
                phase3,
                updated_prompts,
                enable_memory=enable_memory,
                mem_style=mem_style,
                all_memories=memory,
                persona_info_dict=phase3_persona_info,
                old_persona_info_dict=persona_info_dict,
                phase_idx=3,
                enable_pre_feedback=enable_pre_feedback,
                enable_post_feedback=enable_post_feedback,
                feedback_style=feedback_style,
            )
            phase3_results.append(test_set)
            acc, ff = get_metrics(test_set)
            # Calculate ACPE up to current iteration
            acpe_values = calculate_acpe(phase3_results)
            current_acpe = acpe_values[-1] if acpe_values else 0
            write_json(
                test_set,
                os.path.join(
                    cur_dir,
                    f"{output_base}/phase3_iter_{i+1}.json",
                ),
            )

            print(f"Phase 3 iter {i+1}: acc={acc:.3f}, ff={ff:.3f}, ACPE={current_acpe:.3f}")

        # Phase 4: Evaluation only (NO feedback)
        print("\n" + "=" * 70)
        print("Starting Phase 4 evaluation with updated personas...")
        print("=" * 70)

        phase4_persona_info = (
            updated_persona_info_dict
            if updated_persona_info_dict
            else persona_info_dict
        )

        test_set, memory = self.run_study(
            phase4,
            updated_prompts,
            enable_memory=enable_memory,
            mem_style=mem_style,
            all_memories=memory,
            persona_info_dict=phase4_persona_info,
            old_persona_info_dict=persona_info_dict,
            phase_idx=4,
            enable_pre_feedback=False,
            enable_post_feedback=False,
            feedback_style=feedback_style,
        )
        acc, ff = get_metrics(test_set)
        write_json(
            test_set,
            os.path.join(cur_dir, f"{output_base}/phase4.json"),
        )

        print(f"Phase 4: acc={acc:.3f}, ff={ff:.3f}")

        # Save final Phase 3-4 memory checkpoint (for FAISS)
        if enable_memory and memory and mem_style == "faiss":
            # Construct checkpoint path with model info
            if agent_model and human_sim_model:
                final_save_path = os.path.join(
                    cur_dir,
                    f"memory_checkpoints2/shopping/{agent_model}/{human_sim_model}/{mem_style}/{aug_text}/phase3_4_memory",
                )
            else:
                final_save_path = os.path.join(
                    cur_dir,
                    f"memory_checkpoints2/shopping/{mem_style}/{aug_text}/phase3_4_memory",
                )
            os.makedirs(os.path.dirname(final_save_path), exist_ok=True)

            for person_id in memory.keys():
                person_memory = memory[person_id]
                person_final_path = f"{final_save_path}_{person_id}"
                person_memory.save_index(person_final_path)
                print(
                    f"Saved final Phase 3-4 FAISS memory for {person_id} to {person_final_path}"
                )

        print("\n" + "=" * 70)
        print("Phase 3-4 Complete!")
        print("=" * 70)

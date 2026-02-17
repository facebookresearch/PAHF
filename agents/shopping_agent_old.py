import json
import os
import pdb
import sys

sys.path.append("/home/kaiqu/project/agent3")

import json
import pdb
import random
import sqlite3

import time

import faiss

import metagen.bento
import numpy as np

from agent_base import BasePersonalAgent
from agent_utils import (
    get_mc_dataset,
    get_metrics,
    get_option,
    initialize_memory_banks,
    process_mc_raw,
)

from json_utils import write_json

from langchain.embeddings.dragon_plus import DragonPlusEmbedding
from llm import MetaGen

from memory import FAISSMemoryBank, SQLiteMemoryBank
from memory_utils import (
    enhanced_memory_retrieval,
    format_enhanced_memory,
    simple_memory_retrieval,
    store_augmented_memory,
    update_augmented_memory,
)

from metagen import MetaGenKey, RateLimitExceededException
from metagen.types import ChatRole, Message

from prompts.shopping_prompt import (
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


class ShoppingAgent(BasePersonalAgent):
    """Agent for shopping assistance tasks."""

    def __init__(self, metagen):
        """Initialize the shopping agent.

        Args:
            metagen: MetaGen instance for LLM generation
        """
        super().__init__(
            metagen=metagen,
            prompt_summarize=prompt_summarize,
            prompt_question=prompt_question,
            qa_prompt=qa_prompt,
        )

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
    ):
        """Get predictions for test set with memory and feedback."""
        num_test_data = len(test_set)

        for i in range(num_test_data):
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

            gen_text = self.metagen.generate(prompt_final).strip()
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
                    gen_text = self.metagen.generate(prompt_final).strip()
                    action = self.extract_action(gen_text)
                    prompt_final += "\n\n" + gen_text

            # Human decide whether to provide feedback - completely rule-based
            gt_value = test_data.get("gt")
            feedback = ""

            # Only generate feedback if post-feedback is enabled
            if enable_post_feedback:
                if action == "D" and gt_value is not None:
                    # Agent incorrectly chose not to buy, but there's a correct option
                    feedback = f"Option {gt_value} would have worked for me."
                elif action != "D" and action != gt_value and action in ["A", "B", "C"]:
                    # Agent chose wrong option - need to check if it's due to preference change
                    mc_gen_raw = test_data.get("mc_gen_raw")
                    option = mc_gen_raw.split(f"{action})")[1].split("\n")[0].strip()
                    option_features = option.split("with ")[1].split(" and ")

                    # Check if this was correct under old preferences (Phase 3/4 with preference change)
                    preference_changed = False
                    changed_feature = None

                    if (
                        old_persona_info_dict
                        and name in old_persona_info_dict
                        and persona_info_dict
                        and name in persona_info_dict
                    ):
                        # We have both old and new preferences - check for preference change scenario
                        old_prefs = old_persona_info_dict[name].get(
                            test_data["product"], {}
                        )
                        new_prefs = persona_info_dict[name].get(
                            test_data["product"], {}
                        )

                        # Check if this option was acceptable under old preferences
                        was_acceptable_old = True
                        for feature_value in option_features:
                            for feat_category, prefs in old_prefs.items():
                                if feature_value in prefs.get("dislike", []):
                                    was_acceptable_old = False
                                    break
                            if not was_acceptable_old:
                                break

                        # Check if this option is now disliked under new preferences
                        is_disliked_new = False
                        for feature_value in option_features:
                            for feat_category, prefs in new_prefs.items():
                                if feature_value in prefs.get("dislike", []):
                                    # This feature is now disliked
                                    # Check if it was liked in old preferences
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

                        # If agent chose based on old preferences but they've changed
                        if (
                            was_acceptable_old
                            and preference_changed
                            and changed_feature
                        ):
                            feedback = f"Actually, my preferences have changed. I used to like {changed_feature}, but now I don't want it anymore."
                        elif not was_acceptable_old or not preference_changed:
                            # Standard wrong choice feedback - find disliked feature
                            disliked_features = []
                            for feature_value in option_features:
                                for feat_category, prefs in new_prefs.items():
                                    if feature_value in prefs.get("dislike", []):
                                        disliked_features.append(feature_value)
                                        break

                            if disliked_features:
                                feature_str = disliked_features[0]
                                feedback = f"Option {action} won't work for me because I don't want {feature_str}."
                            else:
                                feedback = f"Option {action} doesn't meet my needs."
                    elif persona_info_dict and name in persona_info_dict:
                        # No old preferences available - standard feedback
                        persona_prefs = persona_info_dict[name].get(
                            test_data["product"], {}
                        )

                        # Find which features are disliked
                        disliked_features = []
                        for feature_value in option_features:
                            for feat_category, prefs in persona_prefs.items():
                                if feature_value in prefs.get("dislike", []):
                                    disliked_features.append(feature_value)
                                    break

                        if disliked_features:
                            feature_str = disliked_features[0]
                            feedback = f"Option {action} won't work for me because I don't want {feature_str}."
                        else:
                            feedback = f"Option {action} doesn't meet my needs."
                    else:
                        # Fallback
                        feedback = f"Option {action} doesn't work for me."
                else:
                    # Agent chose correctly or gt is None
                    feedback = random.choice(
                        ["Right!", "Thanks!", "Perfect!", "That works!"]
                    )

            whole_prompt = prompt_final.strip() + (
                f"\n\n" + f"Human: {feedback}" if feedback else ""
            )

            # Check if it should incorporate the feedback into memory
            post_feedback_occurred = 0
            if enable_post_feedback and enable_memory and memory and feedback:
                feedback_prompt = f"{whole_scenario}\n\nHuman feedback: {feedback}\n\nDoes this feedback reveal NEW preference information about product features (not just agreement/disagreement with the agent's action)? Only answer 'Yes' if it states a specific preference, like, dislike, or constraint. Simple confirmations like 'right', 'correct', 'yes', 'none work' should be 'No'. Answer 'Yes' or 'No'."
                check = self.metagen.generate(feedback_prompt)
                if "Yes" in check or "yes" in check:
                    post_feedback_occurred = 1
                    # summarize the feedback
                    summ_prompt = f"{whole_scenario}\n\nHuman feedback: {feedback}\n\n{summ_prompt_template.format(name=name)}"
                    summ_info = self.metagen.generate(summ_prompt)

                    # Universal memory consolidation - always search for similar memory
                    mem_id = memory.find_similar_memory(summ_info)

                    if mem_id is not None:
                        # Found similar memory - check if it's about the same product
                        existing_memory = memory.get_memory(mem_id)

                        product_check_prompt_new = product_check_prompt.format(
                            existing_memory=summ_info, summ_info=existing_memory
                        )
                        product_match = self.metagen.generate(
                            product_check_prompt_new
                        ).strip()

                        if "Yes" in product_match or "yes" in product_match:
                            # Same product - merge the memories using integration prompt
                            merge_prompt = integration_prompt.format(
                                existing_memory=existing_memory, summ_info=summ_info
                            )
                            merged_summary = self.metagen.generate(merge_prompt).strip()
                            (
                                update_augmented_memory(memory, mem_id, merged_summary)
                                if aug_mem
                                else memory.update_memory(mem_id, merged_summary)
                            )
                        else:
                            # Different product - add as new memory
                            (
                                store_augmented_memory(memory, summ_info)
                                if aug_mem
                                else memory.add(summ_info)
                            )
                    else:
                        # No similar memory found - add as new
                        (
                            store_augmented_memory(memory, summ_info)
                            if aug_mem
                            else memory.add(summ_info)
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

            split_str = "\n\n\n"
            scenario = whole_prompt.split(split_str)[-1]
            print(scenario)
            print("------------------")
            print("------------------")

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
    ):
        """Run experiment on data."""
        cur_dir = "/home/kaiqu/project/agent3"
        sys.path.append(cur_dir)

        # Load shopping data from JSON
        test_set = self.load_shopping_data(data_path)

        test_set = test_set[:15]

        test_set, memory = self.get_test_predictions(
            test_set,
            prompt_dict=prompt_dict,
            all_memories=all_memories,
            persona_info_dict=persona_info_dict,
            old_persona_info_dict=old_persona_info_dict,
            enable_memory=enable_memory,
            enable_pre_feedback=enable_pre_feedback,
            enable_post_feedback=enable_post_feedback,
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
        db_path="memory/test_memory.db",
    ):
        """Run a study phase."""
        cur_dir = "/home/kaiqu/project/agent3/memory"
        sys.path.append(cur_dir)

        if enable_memory and enable_pre_feedback and enable_post_feedback:
            aug_text = "pre+post"
        elif enable_memory and enable_pre_feedback:
            aug_text = "pre"
        elif enable_memory and enable_post_feedback:
            aug_text = "post"
        else:
            aug_text = "base"

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
            updated_prompts: Dictionary of prompts for phases 3 & 4 (optional)
            persona_info_dict: Persona info for phases 1 & 2 (optional)
            updated_persona_info_dict: Updated persona info for phases 3 & 4 (optional)
        """
        cur_dir = "/home/kaiqu/project/agent3"
        sys.path.append(cur_dir)

        # Unpack phases
        phase1 = all_phases[0] if len(all_phases) > 0 else None
        phase2 = all_phases[1] if len(all_phases) > 1 else None
        phase3 = all_phases[2] if len(all_phases) > 2 else None
        phase4 = all_phases[3] if len(all_phases) > 3 else None

        if not enable_memory:
            learning_iter = 1

        memory = None

        # Phase 1: Training with feedback (based on flags)
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
                )
                acc, ff, fes = get_metrics(test_set)
                write_json(
                    test_set,
                    os.path.join(
                        cur_dir, f"output/shopping_{mem_style}_phase1_iter_{i+1}.json"
                    ),
                )
                print(f"Phase 1 iter {i+1}: ")
                print(f"acc: {acc}, ff: {ff}, fes: {fes}")

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
        )
        acc, ff, fes = get_metrics(test_set)
        write_json(
            test_set, os.path.join(cur_dir, f"output/shopping_{mem_style}_phase2.json")
        )

        print("Phase 2: ")
        print(f"acc: {acc}, ff: {ff}, fes: {fes}")

        # Phase 3: Training with feedback (based on flags)
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
                )
                acc, ff, fes = get_metrics(test_set)
                write_json(
                    test_set,
                    os.path.join(
                        cur_dir, f"output/shopping_{mem_style}_phase3_iter_{i+1}.json"
                    ),
                )

                print(f"Phase 3 iter {i+1}: ")
                print(f"acc: {acc}, ff: {ff}, fes: {fes}")

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
            )
            acc, ff, fes = get_metrics(test_set)
            write_json(
                test_set,
                os.path.join(cur_dir, f"output/shopping_{mem_style}_phase4.json"),
            )

            print("Phase 4: ")
            print(f"acc: {acc}, ff: {ff}, fes: {fes}")

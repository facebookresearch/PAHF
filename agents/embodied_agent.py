import json
import os
import pdb
import sys

sys.path.append(".")

import json
import pdb
import sqlite3
from typing import Dict, List, Union

import time

import faiss
import numpy as np
from tqdm import tqdm

from agents.base import BasePersonalAgent
from data.embodied.personas.evolved_persona import prompt_evolved_dict
from data.embodied.personas.original_persona import prompt_dict
from memory.banks import FAISSMemoryBank, SQLiteMemoryBank
from memory.utils import (
    enhanced_memory_retrieval,
    format_enhanced_memory,
    simple_memory_retrieval,
    store_augmented_memory,
    update_augmented_memory,
)
from prompts.embodied_prompts import (
    check_update_prompt,
    gt_prompt,
    integration_prompt,
    judge_prompt,
    keyword_prompt,
    mc_gen_prompt_template,
    opt_q,
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


def scenario_to_text(scenario: Dict) -> str:
    """Convert a JSON scenario dict to text format for internal processing.
    
    Args:
        scenario: Dictionary with keys: index, scene, task, context, user,
                  user_intent_object, user_intent_location, scene_objects
    
    Returns:
        Text representation for internal processing
    """
    lines = [
        str(scenario.get("index", 0)),
        f"Scene: {scenario.get('scene', '')}",
        f"Task: {scenario.get('task', '')}",
        f"Context: {scenario.get('context', '')}",
        f"User: {scenario.get('user', '')}",
        f"User intent (object): {scenario.get('user_intent_object', '')}",
        f"User intent (location): {scenario.get('user_intent_location', '')}",
        f"Scene objects: {', '.join(scenario.get('scene_objects', []))}"
    ]
    return "\n".join(lines)


def load_dataset(file_path: str) -> List[str]:
    """Load dataset from JSON file.
    
    Args:
        file_path: Path to the JSON dataset file
        
    Returns:
        List of scenario texts for internal processing
    """
    with open(file_path, "r", encoding="utf-8") as f:
        scenarios = json.load(f)
    return [scenario_to_text(s) for s in scenarios]


class EmbodiedAgent(BasePersonalAgent):
    """Agent for embodied/robot tasks."""

    def __init__(self, llm_client):
        """Initialize the embodied agent.

        Args:
            llm_client: LLM client instance for generation
        """
        super().__init__(
            llm_client=llm_client,
            prompt_summarize=prompt_summarize,
            prompt_question=prompt_question,
            qa_prompt=qa_prompt,
        )

    def get_agent_type(self) -> str:
        """Return the agent type name."""
        return "Robot"

    def get_gt(self, test_data, whole_scenario):
        """Get ground truth for a test case."""
        info = test_data["info"]
        obj = info.split("User intent (object): ")[-1].split("\n")[0].strip()
        loc = info.split("User intent (location): ")[-1].split("\n")[0].strip()
        loc_info = "no specific location" if "pick-up" in loc else loc
        gt_info = gt_prompt.format(obj, loc_info)
        messages = [
            {"role": "system", "content": judge_prompt},
            {
                "role": "user",
                "content": whole_scenario + "\n" + gt_info + "\n\n" + opt_q,
            },
        ]
        gt_opt = self.llm_client.generate(messages).strip()
        return gt_opt

    def get_test_predictions(
        self,
        test_set,
        all_memories,
        prompt_dict,
        enable_pre_feedback=True,
        enable_post_feedback=True,
        enable_memory=True,
        keep_whole_memory=True,
        aug_mem=False,
    ):
        """Get predictions for test set with memory and feedback."""
        num_test_data = len(test_set)

        for i in tqdm(range(num_test_data), desc="Processing tasks"):
            test_data = test_set[i]

            whole_scenario = test_data["mc_gen_raw"].strip()
            scenario = whole_scenario.split("Options:")[0].strip()
            scene = scenario.split("Scene: ")[1].split("\n")[0].strip()
            mc_gen_all = process_mc_raw(whole_scenario)

            # Get the human persona
            name = scenario.split("\n")[1].split(": ")[0]
            task = scenario.split("\n")[1].split(": ")[1]
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
                task_query = f"Scene: {scene}\n{name}: {task}"
                context_str = self.retrieve_memory_context(
                    memory, task_query, whole_scenario
                )
                if context_str:
                    prompt_final += "\n\n" + context_str

            gen_text = self.llm_client.generate(prompt_final).strip()
            action = self.extract_action(gen_text)
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

            if action not in letter_option:
                final_action = "None"
            else:
                final_action = (
                    "Ask human for feedback"
                    if action == "Ask human"
                    else letter_option[action]
                )

            # Human decide whether to provide feedback
            feedback = ""
            if enable_post_feedback:
                messages = [
                    {"role": "system", "content": prompt_human},
                    {
                        "role": "user",
                        "content": scenario + "\n\n" + f"Robot Action: {final_action}",
                    },
                ]
                feedback = self.llm_client.generate(messages)

            whole_prompt = prompt_final.strip() + (
                f"\n\n" + f"Human: {feedback}" if feedback else ""
            )

            # Check if it should incorporate the feedback into memory
            post_feedback_occurred = 0
            if enable_post_feedback and enable_memory and memory and feedback:
                feedback_prompt = f"Human feedback: {feedback}.\nDoes the feedback contain any personalized information? Answer a single word 'Yes' or 'No'."
                check = self.llm_client.generate(feedback_prompt)
                if "Yes" in check or "yes" in check:
                    post_feedback_occurred = 1
                    # summarize the feedback
                    summ_prompt = f"Human feedback: {feedback}\n{summ_prompt_template.format(name=name)}"
                    summ_info = self.llm_client.generate(summ_prompt)

                    # check update
                    check_update_prompt_full = (
                        f"Human feedback: {feedback}.\n{check_update_prompt}"
                    )
                    check_update = self.llm_client.generate(check_update_prompt_full)
                    if "Yes" in check_update or "yes" in check_update:
                        update_prompt = update_prompt_template.format(name=name)
                        # Find the most similar memory
                        retrieve_prev_pref_prompt = (
                            f"Human feedback: {feedback}\n{update_prompt}"
                        )
                        prev_pref_info = self.llm_client.generate(
                            retrieve_prev_pref_prompt
                        )
                        mem_id = memory.find_similar_memory(prev_pref_info)
                        if mem_id is not None:
                            if keep_whole_memory:
                                existing_memory = memory.get_memory(mem_id)
                                summ_prompt2 = integration_prompt.format(
                                    existing_memory=existing_memory, summ_info=summ_info
                                )
                                new_summary = self.llm_client.generate(
                                    summ_prompt2
                                ).strip()
                                (
                                    update_augmented_memory(
                                        memory, mem_id, summ_info, self.llm_client
                                    )
                                    if aug_mem
                                    else memory.update_memory(mem_id, new_summary)
                                )
                            else:
                                (
                                    update_augmented_memory(
                                        memory, mem_id, summ_info, self.llm_client
                                    )
                                    if aug_mem
                                    else memory.update_memory(mem_id, summ_info)
                                )
                        else:
                            # No similar memory found — add as new memory
                            (
                                store_augmented_memory(
                                    memory, summ_info, self.llm_client
                                )
                                if aug_mem
                                else memory.add(summ_info)
                            )
                    else:
                        (
                            store_augmented_memory(memory, summ_info, self.llm_client)
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
            test_data["aciton"] = action

            info = test_set[i]["info"]
            test_data["whole_prompt"] = whole_prompt
            test_data["human_feedback"] = feedback
            test_data["memory_enabled"] = enable_memory

        return test_set, all_memories

    def run_exp(
        self,
        data_dir,
        all_memories,
        prompt_dict,
        enable_memory=True,
        enable_pre_feedback=True,
        enable_post_feedback=True,
    ):
        """Run experiment on data."""
        cur_dir = "."
        sys.path.append(cur_dir)

        scenario_info_path = os.path.join(cur_dir, data_dir)
        # Load scenarios from JSON dataset
        scenario_info_text = load_dataset(scenario_info_path)

        test_set = self.get_init_prompt_chat(
            scenario_info_text, scenario_test_prompt, mc_gen_prompt_template
        )

        test_set = get_mc_dataset(test_set, self.llm_client)
        test_set, memory = self.get_test_predictions(
            test_set,
            prompt_dict=prompt_dict,
            all_memories=all_memories,
            enable_memory=enable_memory,
            enable_pre_feedback=enable_pre_feedback,
            enable_post_feedback=enable_post_feedback,
        )

        return test_set, memory

    def get_init_prompt_chat(
        self, scenario_info_text, scenario_test_prompt, mc_gen_prompt_template
    ):
        """Initialize prompt chat from scenario information."""
        mc_gen_prompt_test = []
        num_data = len(scenario_info_text)

        for i in range(num_data):
            scenario_text = scenario_info_text[i]

            scene_descriptions = scenario_text.split("\n")[1].split("Scene: ")[1]

            instruction = scenario_text.split("\n")[2].split("Task: ")[1]
            name = scenario_text.split("\n")[4].split("User: ")[1]

            new_prompt = scenario_test_prompt.format(
                scene_descriptions, name, instruction
            )
            msg = mc_gen_prompt_template.strip() + "\n\n" + new_prompt
            mc_gen_prompt_test.append(msg)

        test_set = []
        for i in range(num_data):
            test_set.append(
                {
                    "info": scenario_info_text[i],
                    "mc_gen_prompt": mc_gen_prompt_test[i],
                }
            )
        return test_set

    def run_study(
        self,
        data_dir,
        prompts,
        enable_memory=True,
        mem_style="sql",
        all_memories=None,
        phase_idx=1,
        enable_pre_feedback=True,
        enable_post_feedback=True,
        db_path="memory/test_memory.db",
    ):
        """Run a study phase."""
        cur_dir = "./memory"
        sys.path.append(cur_dir)

        # PAHF uses both pre-action and post-action feedback with memory
        aug_text = "pahf" if enable_memory else "base"

        if all_memories is None:
            all_memories = initialize_memory_banks(
                prompts, mem_style, cur_dir, f"embodied_agent_{aug_text}"
            )

        test_set, all_memories = self.run_exp(
            data_dir,
            all_memories=all_memories,
            prompt_dict=prompts,
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
    ):
        """Run full study with multiple phases.

        Args:
            all_phases: List of [phase1, phase2, phase3, phase4]
            prompts: Dict with 'original' and 'evolved' keys
            enable_memory: Whether to use memory
            mem_style: 'sql' or 'faiss'
            learning_iter: Number of iterations for phases 1 and 3
            enable_pre_feedback: Enable pre-action feedback for phases 1 and 3
            enable_post_feedback: Enable post-action feedback for phases 1 and 3
        """
        cur_dir = "."
        sys.path.append(cur_dir)
        phase1, phase2, phase3, phase4 = all_phases
        prompt_human = prompts["original"]
        prompt_human_evolved = prompts["evolved"]

        # PAHF uses both pre-action and post-action feedback with memory
        aug_text = "pahf" if enable_memory else "base"

        if not enable_memory:
            learning_iter = 1

        memory = None

        # Phase 1: Training with feedback (based on flags)
        print("\n" + "=" * 50)
        print("PHASE 1: Training with original personas")
        print("=" * 50)
        phase1_results = []  # Track results for ACPE calculation
        for i in range(learning_iter):
            print(f"\n--- Phase 1, Iteration {i+1}/{learning_iter} ---")
            test_set, memory = self.run_study(
                phase1,
                prompt_human,
                enable_memory=enable_memory,
                mem_style=mem_style,
                all_memories=memory,
                phase_idx=1,
                enable_pre_feedback=enable_pre_feedback,
                enable_post_feedback=enable_post_feedback,
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
                    f"output/embodied/{mem_style}/{aug_text}/phase1_iter_{i+1}.json",
                ),
            )

            print(f"Phase 1 iter {i+1}: acc={acc:.3f}, ff={ff:.3f}, ACPE={current_acpe:.3f}")

        # Phase 2: Evaluation only (NO feedback)
        print("\n" + "=" * 50)
        print("PHASE 2: Evaluation with original personas (no feedback)")
        print("=" * 50)
        test_set, memory = self.run_study(
            phase2,
            prompt_human,
            enable_memory=enable_memory,
            mem_style=mem_style,
            all_memories=memory,
            phase_idx=2,
            enable_pre_feedback=False,  # No feedback in test phase
            enable_post_feedback=False,  # No feedback in test phase
        )
        acc, ff = get_metrics(test_set)
        write_json(
            test_set,
            os.path.join(
                cur_dir, f"output/embodied/{mem_style}/{aug_text}/phase2.json"
            ),
        )

        print(f"Phase 2: acc={acc:.3f}, ff={ff:.3f}")

        # Phase 3: Training with feedback (based on flags)
        print("\n" + "=" * 50)
        print("PHASE 3: Training with evolved personas")
        print("=" * 50)
        phase3_results = []  # Track results for ACPE calculation
        for i in range(learning_iter):
            print(f"\n--- Phase 3, Iteration {i+1}/{learning_iter} ---")
            test_set, memory = self.run_study(
                phase3,
                prompt_human_evolved,
                enable_memory=enable_memory,
                mem_style=mem_style,
                all_memories=memory,
                phase_idx=3,
                enable_pre_feedback=enable_pre_feedback,
                enable_post_feedback=enable_post_feedback,
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
                    f"output/embodied/{mem_style}/{aug_text}/phase3_iter_{i+1}.json",
                ),
            )

            print(f"Phase 3 iter {i+1}: acc={acc:.3f}, ff={ff:.3f}, ACPE={current_acpe:.3f}")

        # Phase 4: Evaluation only (NO feedback)
        print("\n" + "=" * 50)
        print("PHASE 4: Evaluation with evolved personas (no feedback)")
        print("=" * 50)
        test_set, memory = self.run_study(
            phase4,
            prompt_human_evolved,
            enable_memory=enable_memory,
            mem_style=mem_style,
            all_memories=memory,
            phase_idx=4,
            enable_pre_feedback=False,  # No feedback in test phase
            enable_post_feedback=False,  # No feedback in test phase
        )
        acc, ff = get_metrics(test_set)
        write_json(
            test_set,
            os.path.join(
                cur_dir, f"output/embodied/{mem_style}/{aug_text}/phase4.json"
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
        memory_save_path=None,
    ):
        """Run Phase 1 and Phase 2, save memory for later use.

        Args:
            phase1: Path to phase 1 data
            phase2: Path to phase 2 data
            prompts: Dictionary of prompts
            enable_memory: Whether to use memory
            mem_style: Memory style ('sql' or 'faiss')
            learning_iter: Number of learning iterations for phase 1
            enable_pre_feedback: Enable pre-action feedback for phase 1
            enable_post_feedback: Enable post-action feedback for phase 1
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
                f"embodied_{mem_style}_{aug_text}",
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
            output_base = f"output2/embodied/{agent_model}/{human_sim_model}/{mem_style}/{aug_text}"
        else:
            output_base = f"output2/embodied/{mem_style}/{aug_text}"

        phase1_results = []
        for i in range(learning_iter):
            test_set, memory = self.run_study(
                phase1,
                prompts,
                enable_memory=enable_memory,
                mem_style=mem_style,
                all_memories=memory,
                phase_idx=1,
                enable_pre_feedback=enable_pre_feedback,
                enable_post_feedback=enable_post_feedback,
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
            phase_idx=2,
            enable_pre_feedback=False,
            enable_post_feedback=False,
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
                    f"memory_checkpoints2/embodied/{mem_style}/{aug_text}/phase1_2_memory",
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
                # For SQL, the database file is already persisted
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
        prompts_evolved,
        enable_memory=True,
        mem_style="sql",
        learning_iter=3,
        enable_pre_feedback=True,
        enable_post_feedback=True,
        memory_load_path=None,
        db_path=None,
    ):
        """Load memory from Phase 1-2 and run Phase 3 and Phase 4.

        Args:
            phase3: Path to phase 3 data
            phase4: Path to phase 4 data
            prompts_evolved: Dictionary of evolved prompts for phases 3 & 4
            enable_memory: Whether to use memory
            mem_style: Memory style ('sql' or 'faiss')
            learning_iter: Number of learning iterations for phase 3
            enable_pre_feedback: Enable pre-action feedback for phase 3
            enable_post_feedback: Enable post-action feedback for phase 3
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
                            f"memory2/{agent_model}/{human_sim_model}/{mem_style}/embodied_{mem_style}_{aug_text}",
                        )
                    else:
                        # Fallback to old structure
                        memory_load_path = os.path.join(
                            cur_dir,
                            f"memory2/{mem_style}/embodied_{mem_style}_{aug_text}",
                        )

                # Get persona names from prompts_evolved
                memory = {}
                for person_id in prompts_evolved.keys():
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
                            f"memory2/{agent_model}/{human_sim_model}/{mem_style}/embodied_{mem_style}_{aug_text}_memory.db",
                        )
                    else:
                        # Fallback to old structure
                        db_path = os.path.join(
                            cur_dir,
                            f"memory2/{mem_style}/embodied_{mem_style}_{aug_text}_memory.db",
                        )

                memory = {}
                from memory import SQLiteMemoryBank

                for person_id in prompts_evolved.keys():
                    memory[person_id] = SQLiteMemoryBank(
                        db_path=db_path, person_id=person_id
                    )
                print(f"Loaded SQLite memory from: {db_path}")

        # Phase 3: Training with feedback
        print("\n" + "=" * 70)
        print("Starting Phase 3 training with evolved personas...")
        print("=" * 70)

        # Construct output directory with model info
        if agent_model and human_sim_model:
            output_base = f"output2/embodied/{agent_model}/{human_sim_model}/{mem_style}/{aug_text}"
        else:
            output_base = f"output2/embodied/{mem_style}/{aug_text}"

        phase3_results = []
        for i in range(learning_iter):
            test_set, memory = self.run_study(
                phase3,
                prompts_evolved,
                enable_memory=enable_memory,
                mem_style=mem_style,
                all_memories=memory,
                phase_idx=3,
                enable_pre_feedback=enable_pre_feedback,
                enable_post_feedback=enable_post_feedback,
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
        print("Starting Phase 4 evaluation with evolved personas...")
        print("=" * 70)

        test_set, memory = self.run_study(
            phase4,
            prompts_evolved,
            enable_memory=enable_memory,
            mem_style=mem_style,
            all_memories=memory,
            phase_idx=4,
            enable_pre_feedback=False,
            enable_post_feedback=False,
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
                    f"memory_checkpoints2/embodied/{agent_model}/{human_sim_model}/{mem_style}/{aug_text}/phase3_4_memory",
                )
            else:
                final_save_path = os.path.join(
                    cur_dir,
                    f"memory_checkpoints2/embodied/{mem_style}/{aug_text}/phase3_4_memory",
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

mc_gen_prompt_template = """You are simulating an AI shopping agent that helps users buy products in an online shopping system. The agent can select from various product options or decline to purchase if none meet requirements.

PRODUCT CATEGORIES:
- Headphones (wearing style, acoustic principle, connectivity mode, control interface, audio environment feature)
- TVs (smart OS, panel technology, base type, tuner standard, speaker orientation)
- Refrigerators (door configuration, cooling architecture, storage organization, ice/water system, user interface)
- Cameras (image sensor, lens mount, viewfinding method, shutter mechanism, storage medium)
- Dishwashers (installation format, water distribution, drying technology, soil filtration, detergent delivery)
- Air Conditioners (cooling mechanism, installation configuration, airflow distribution, control interface, refrigerant)
- Washing Machines (loading mechanism, washing motion, control interface, water supply, drying method)
- Microwave Ovens (heating mechanism, door configuration, control interface, cavity material, cooking control)
- Smartphones (interaction modality, biometric authentication, camera modules, battery architecture, form factor)
- Laptops (form factor, charging adapter, webcam placement, keyboard technology, speaker placement)

The agent can select products based on user preferences or choose not to buy if no option satisfies requirements.
Please generate the options for the scenario given the previous examples.

Emma: I'd like to get headphones that match my style
Options:
A) headphones with bluetooth link and bone-conduction frame
B) headphones with wired connection and ear-hook in-ear design
C) headphones with 2.4 GHz low-latency dongle and in-ear design
D) Do not buy anything

Liam: Help me purchase a TV that I'd like
Options:
A) TV with 55-inch OLED panel and webOS platform
B) TV with 65-inch LCD panel and Roku TV platform
C) TV with 48-inch QLED panel and Fire TV platform
D) Do not buy anything

Sophia: I'm looking for a refrigerator that suits my needs
Options:
A) refrigerator with french-door layout and inverter compressor loop
B) refrigerator with side-by-side structure and dual-evaporator inverter system
C) refrigerator with top-freezer layout and absorption cooling system
D) Do not buy anything

Noah: Help me get a camera that fits my preferences
Options:
A) camera with backside-illuminated CMOS sensor and Canon EF mount
B) camera with Foveon X3 sensor and Sony E mount
C) camera with front-side illuminated CMOS sensor and Nikon F mount
D) Do not buy anything
"""


prompt_react = """You are an AI shopping agent that helps users buy products in an online shopping system.

PRODUCT CATEGORIES:
- Headphones (wearing style, acoustic principle, connectivity mode, control interface, audio environment feature)
- TVs (smart OS, panel technology, base type, tuner standard, speaker orientation)
- Refrigerators (door configuration, cooling architecture, storage organization, ice/water system, user interface)
- Cameras (image sensor, lens mount, viewfinding method, shutter mechanism, storage medium)
- Dishwashers (installation format, water distribution, drying technology, soil filtration, detergent delivery)
- Air Conditioners (cooling mechanism, installation configuration, airflow distribution, control interface, refrigerant)
- Washing Machines (loading mechanism, washing motion, control interface, water supply, drying method)
- Microwave Ovens (heating mechanism, door configuration, control interface, cavity material, cooking control)
- Smartphones (interaction modality, biometric authentication, camera modules, battery architecture, form factor)
- Laptops (form factor, charging adapter, webcam placement, keyboard technology, speaker placement)

The agent can select products based on user preferences or choose not to buy if no option satisfies requirements.

TASK INSTRUCTIONS:
You must determine the next action to complete the given purchase task.
- If the task is clear and you have preference information, select the appropriate product option.
- If the task involves personalization, search memory for relevant preference information.
- If preferences are unclear or missing, ask the user for clarification.

WHEN TO ASK FOR CLARIFICATION:
You MUST ask for clarification when:
1. The task involves subjective preferences
2. The task doesn't provide enough information to determine which product features the user wants
3. You don't have relevant preference information in memory to make the decision
4. The task is unclear or ambiguous

CRITICAL PURCHASING RULE — ALL FEATURES REQUIREMENT:
⚠️ You MUST buy a product (select A, B, or C) ONLY if ALL features listed in the option match the user's preferred/acceptable features.
- Each option lists multiple features — evaluate every feature that is explicitly stated
- Count how many listed features in each option match the user's stated or remembered preferences
- If an option has ALL listed features matching → SELECT THAT OPTION
- If NO option has all listed features matching → SELECT OPTION D (Do not buy anything)
- Note: Some examples below may show fewer features for brevity; in the benchmark, evaluate all features provided in each option (typically 3), and ALL must match

WHEN TO SELECT "D) Do not buy anything":
You should select option D when:
- None of the available product options (A, B, or C) have ALL features that match the user's preferences
- All available options contain features that contradict the user's known preferences
- The user's requirements cannot be satisfied by any of the presented options

FORMAT REQUIREMENTS:
Your response must ALWAYS follow this exact format:

Thought: <detailed reasoning explaining your decision process>
Action: <EITHER a specific option letter (A, B, C, D), OR "Ask human">

IMPORTANT: Do NOT add any empty lines between the Thought and Action fields. DO NOT generate Question: or Summary: fields.

IMPORTANT RULES:
- Never skip any of the two required fields
- For Action, only use option letters (A, B, C, D) or the exact phrase "Ask human"
- Always provide detailed reasoning in your Thought field
- After receiving clarification from a human (marked with "Human:"), select the appropriate action option
- Remember that option D means "Do not buy anything" - use it when no product matches user preferences
- ⚠️ CRITICAL: You can ask the human AT MOST ONE QUESTION per task. After receiving one answer from the human, you MUST make a decision and select an action (A, B, C, or D). No further questions are allowed.

EXAMPLES:

Example 1:
Emma: I'd like to get headphones that match my style
Options:
A) headphones with bluetooth link and bone-conduction frame
B) headphones with wired connection and ear-hook in-ear design
C) headphones with 2.4 GHz low-latency dongle and in-ear design
D) Do not buy anything

Context: No relevant personalized information found in memory.

Thought: The task asks for headphones that match Emma's style, but I don't know what her preferred features are. Without this information, I cannot determine which option (A, B, C, or D) is correct.
Action: Ask human

Question: What connectivity mode do you prefer for headphones? (bluetooth, wired, 2.4 GHz dongle, or RF transmitter)
Human: I prefer RF transmitter connectivity

Thought: Now I know Emma prefers RF transmitter connectivity. Looking at the options, none of them have RF transmitter connectivity. Option A has bluetooth, Option B has wired, and Option C has 2.4 GHz dongle. Since none match her preferred RF transmitter connectivity, I should select option D to not buy anything.
Action: D

Example 2:
Liam: Help me purchase a TV that I'd like
Options:
A) TV with 55-inch OLED panel and webOS platform
B) TV with 65-inch LCD panel and Roku TV platform
C) TV with 48-inch QLED panel and Fire TV platform
D) Do not buy anything

Context: Liam prefers 55-inch OLED panel for TVs.

Thought: I need to ask about Liam's TV preferences about platform to make the right choice.
Action: Ask human

Question: What smart TV platform do you prefer? (webOS, Roku TV, Fire TV, or other)
Human: I prefer webOS platform

Thought: Liam has clarified that he prefers webOS platform. Option A has both OLED panel and webOS platform, which matches his stated preference. This is the best match among the available options.
Action: A

Example 3:
Sophia: I'm looking for a refrigerator that suits my needs
Options:
A) refrigerator with french-door layout and inverter compressor loop
B) refrigerator with side-by-side structure and dual-evaporator inverter system
C) refrigerator with top-freezer layout and absorption cooling system
D) Do not buy anything

Context: Sophia prefers top-freezer layout and inverter compressor loop for refrigerators.

Thought: Based on the context, Sophia prefers top-freezer layout and inverter compressor loop. Looking at the options: Option A has the inverter compressor loop but uses french-door layout instead of top-freezer. Option C has the top-freezer layout but uses absorption cooling instead of inverter compressor. Option B doesn't match either preference. None of the options provide both features Sophia is looking for, so I should select option D.
Action: D

Example 4:
Oliver: Help me choose a washing machine that works for me
Options:
A) washing machine with front-load design and steam cycle feature
B) washing machine with top-load design and steam cycle feature
C) washing machine with front-load design and bleach dispenser
D) Do not buy anything

Context: Oliver prefers front-load design and steam cycle feature for washing machines.

Thought: Oliver is looking for front-load design and steam cycle feature. Option A has both the front-load design and steam cycle feature that Oliver wants. Option B only has the steam cycle but uses top-load instead. Option C has the front-load design but lacks the steam cycle. Option A satisfies both of Oliver's requirements.
Action: A

Example 5:
Noah: Help me get a camera that fits my preferences
Options:
A) camera with backside-illuminated CMOS sensor and Canon EF mount
B) camera with Foveon X3 sensor and Sony E mount
C) camera with front-side illuminated CMOS sensor and Nikon F mount
D) Do not buy anything

Context: Noah prefers organic photoconductive film sensor and Canon EF mount for cameras.

Thought: Noah is looking for organic photoconductive film sensor and Canon EF mount. Option A has the Canon EF mount but uses backside-illuminated CMOS sensor instead of the organic photoconductive film sensor Noah prefers. Options B and C don't have either feature Noah wants. Since none of the options have both the sensor type and mount that Noah prefers, I should select option D.
Action: D
"""


prompt_question = """You are an AI shopping agent that helps users buy products in an online shopping system.

PRODUCT CATEGORIES:
- Headphones (wearing style, acoustic principle, connectivity mode, control interface, audio environment feature)
- TVs (smart OS, panel technology, base type, tuner standard, speaker orientation)
- Refrigerators (door configuration, cooling architecture, storage organization, ice/water system, user interface)
- Cameras (image sensor, lens mount, viewfinding method, shutter mechanism, storage medium)
- Dishwashers (installation format, water distribution, drying technology, soil filtration, detergent delivery)
- Air Conditioners (cooling mechanism, installation configuration, airflow distribution, control interface, refrigerant)
- Washing Machines (loading mechanism, washing motion, control interface, water supply, drying method)
- Microwave Ovens (heating mechanism, door configuration, control interface, cavity material, cooking control)
- Smartphones (interaction modality, biometric authentication, camera modules, battery architecture, form factor)
- Laptops (form factor, charging adapter, webcam placement, keyboard technology, speaker placement)

⚠️⚠️⚠️ CRITICAL INSTRUCTION: OUTPUT ONLY THE QUESTION - NOTHING ELSE ⚠️⚠️⚠️

TASK INSTRUCTIONS:
When faced with unclear product preferences, you must generate a precise question that directly addresses the missing information. Your question should:
1. Ask about ONLY ONE SPECIFIC FEATURE at a time (this reduces the burden on humans)
2. Be very concise and targeted
3. List the relevant options for that specific feature
4. Be phrased in a way that's easy for a user to answer with minimal effort

CRITICAL RULES:
- Ask about ONE feature only per question (e.g., ask about "connectivity mode" OR "wearing style", not both)
- Keep the question as short and simple as possible
- Do NOT ask compound questions about multiple features
- Focus on the most important missing preference first

FORMAT REQUIREMENTS:
Your response must ONLY contain the question in this EXACT format:

Question: <Concise question asking about ONE specific feature with relevant options listed>

DO NOT include any other text, explanations, thoughts, or actions in your response.
DO NOT include words like "Thought:" or "Action:" in your response.
ONLY output the Question: line and nothing else.

EXAMPLES:

Example 1:
Emma: I'd like to get headphones that match my style
Options:
A) headphones with bluetooth link and bone-conduction frame
B) headphones with wired connection and ear-hook in-ear design
C) headphones with 2.4 GHz low-latency dongle and in-ear design
D) Do not buy anything

Question: What connectivity mode do you prefer for headphones? (bluetooth, wired, 2.4 GHz dongle, or RF transmitter)

Example 2:
Liam: Help me purchase a TV that I'd like
Options:
A) TV with 55-inch OLED panel and webOS platform
B) TV with 65-inch LCD panel and Roku TV platform
C) TV with 48-inch QLED panel and Fire TV platform
D) Do not buy anything

Question: What smart TV platform do you prefer? (webOS, Roku TV, Fire TV, or other)
"""


prompt_summarize = """You are an AI shopping agent that helps users buy products in an online shopping system.

PRODUCT CATEGORIES:
- Headphones (wearing style, acoustic principle, connectivity mode, control interface, audio environment feature)
- TVs (smart OS, panel technology, base type, tuner standard, speaker orientation)
- Refrigerators (door configuration, cooling architecture, storage organization, ice/water system, user interface)
- Cameras (image sensor, lens mount, viewfinding method, shutter mechanism, storage medium)
- Dishwashers (installation format, water distribution, drying technology, soil filtration, detergent delivery)
- Air Conditioners (cooling mechanism, installation configuration, airflow distribution, control interface, refrigerant)
- Washing Machines (loading mechanism, washing motion, control interface, water supply, drying method)
- Microwave Ovens (heating mechanism, door configuration, control interface, cavity material, cooking control)
- Smartphones (interaction modality, biometric authentication, camera modules, battery architecture, form factor)
- Laptops (form factor, charging adapter, webcam placement, keyboard technology, speaker placement)

TASK INSTRUCTIONS:
Create a comprehensive summary of ALL information retrieved from memory that is relevant to the purchase task.

⚠️ CRITICAL REQUIREMENTS - INFORMATION PRESERVATION:
1. Include EVERY preference, like, dislike, constraint, and requirement that is RELEVANT to the product features mentioned in the options
2. Do NOT include information that is unrelated to the features in the available options (e.g., if options only show connectivity and design, don't include unrelated info like color preferences or budget)
3. If a user has multiple preferences about the same feature type, include ALL of them
4. Preserve specific feature names and values (e.g., "bluetooth connectivity", "OLED panel")
5. If the context mentions both what the user likes AND dislikes about relevant features, include BOTH
6. Use multiple sentences if needed to capture all relevant information - do not compress at the cost of losing details
7. If no relevant information exists, output 'No relevant personalized information found in memory.'

COMPREHENSIVENESS OVER BREVITY: Your goal is to ensure the agent has access to ALL available preference information that is relevant to the features in the options. A longer, complete summary with all relevant details is better than a shorter summary that loses information.

FORMAT REQUIREMENTS:
Your response must ONLY contain the summary in this EXACT format:

Summary: <your comprehensive summary here - include all details>

EXAMPLES:

Example 1:
Emma: I'd like to get headphones that match my style
Options:
A) headphones with bluetooth link and bone-conduction frame
B) headphones with wired connection and ear-hook in-ear design
C) headphones with 2.4 GHz low-latency dongle and in-ear design
D) Do not buy anything

Context:
None

Summary: No relevant personalized information found in memory

Example 2:
Liam: Help me purchase a TV that I'd like
Options:
A) TV with 55-inch OLED panel and webOS platform
B) TV with 65-inch LCD panel and Roku TV platform
C) TV with 48-inch QLED panel and Fire TV platform
D) Do not buy anything

Context:
- Liam prefers webOS platform for TVs.

Summary: Liam prefers webOS platform for TVs.

Example 3:
Sophia: I'm looking for a refrigerator that suits my needs
Options:
A) refrigerator with french-door layout and inverter compressor loop
B) refrigerator with side-by-side structure and dual-evaporator inverter system
C) refrigerator with top-freezer layout and absorption cooling system
D) Do not buy anything

Context:
- Sophia prefers top-freezer layout for refrigerators.
- Sophia likes inverter compressor loop for cooling.
- Sophia never uses water dispensers.

Summary: Sophia prefers top-freezer layout and inverter compressor loop for refrigerators, and never uses water dispensers.

Example 4:
Marcus: Find me a laptop that fits my work style
Options:
A) laptop with 2-in-1 convertible form and USB-C charging adapter
B) laptop with clamshell design and proprietary charging adapter
C) laptop with detachable keyboard form and wireless charging pad
D) Do not buy anything

Context:
- Marcus prefers 2-in-1 convertible laptops because he works from multiple locations including coffee shops and co-working spaces, values portability and flexibility in his devices, and finds that 2-in-1 convertibles work well for both typing and presentations, though he previously owned a detachable keyboard laptop and found the connection unreliable.
- Marcus uses USB-C charging for all his devices to minimize cable clutter.
- Marcus dislikes proprietary charging adapters because they're hard to replace when traveling.

Summary: Marcus prefers 2-in-1 convertible laptops and previously owned a detachable keyboard laptop but found the connection unreliable. Marcus uses USB-C charging adapters and dislikes proprietary charging adapters.
"""


scenario_test_prompt = """{}: {}
Options:
A)
B)
C)
D)

ONLY fill in the answer options (A, B, C, D) above for the last scenario. DO NOT generate new purchase tasks. STOP after listing the options.
"""

scenario_gen_prompt = """Explain:
Prediction:

Given the scenario, task, and options provided, ONLY fill in the blanks after 'Explain:' and 'Prediction:' for the last scenario. DO NOT create new purchase tasks or options.
"""

qa_prompt = """Question: {}
Human: {}"""


judge_prompt = """You are acting as an impartial judge evaluating which product option is correct based on ground truth information. Your task is to select the most appropriate option that aligns with the provided user preferences.

## Instructions:

1. Carefully read the purchase task and available product options.
2. Review the ground truth information that specifies the user's preferred product features.
3. Determine which option correctly matches the user's preferences given the ground truth information.
4. If none of the options match the ground truth preferences, select option D (Do not buy anything).

## Selection Rules:

- If the task clearly matches user preferences with one of the product options (A, B, or C), select that option.
- If the task contains preference-based requests (e.g., "that I like", "that matches my style") and the ground truth specifies preferences not met by any option, select D.
- If the task involves subjective preferences and the ground truth specifies particular features, select the option that best matches those features, or D if none match.
- Option D means "Do not buy anything" and should be selected when no product option satisfies the user's requirements.

## Response Format:

Your response must be ONLY a single capital letter representing the correct option (A, B, C, or D).
Do not include any other text, explanations, or formatting - just the letter.

## Example:

Emma: I'd like to get headphones that match my style
Options:
A) headphones with bluetooth link and bone-conduction frame
B) headphones with wired connection and ear-hook in-ear design
C) headphones with 2.4 GHz low-latency dongle and in-ear design
D) Do not buy anything
Ground truth information:
User prefers: RF transmitter connectivity and in-ear design

What is the correct option?
D
"""

gt_prompt = """Ground truth information:
User prefers: {}"""

opt_q = "What is the correct option?"

######### Memory prompts #########
update_prompt_template = """According to the human feedback, please summarize the previous {name} preference in one brief sentence.

Example:
Human feedback: You might not know that I changed my previous preference for OLED TVs, but now I prefer QLED. Could you get me that instead?

Output: {name} preferred OLED TVs"""

summ_prompt_template = "According to the human feedback, please summarize the personalized information about {name} in one brief, concise sentence. Keep the summary very short and targeted. If this involves a change in preference, include what changed."


check_update_prompt = """Does this feedback CHANGE a previously stated preference? Look for phrases indicating a transition from one preference to another:
- "but now..." / "now I prefer..."
- "used to like X, but..."
- "changed my mind about..."
- "instead of X, I prefer Y"
- "no longer like..."

If it's just adding NEW information or conditional preferences (e.g., "I like X for home use"), answer 'No'.

Answer a single word 'Yes' or 'No'."""


keyword_prompt = """Generate task-relevant keywords that would help retrieve this memory for specific shopping tasks/situations:
- What product features would this be relevant for?
- What product categories or types?
- What situations or use cases?

Examples:
Memory: "Emma prefers in-ear design for headphones" → "headphones, earphones, audio, in-ear, wearing style, portable audio, music"
Memory: "Liam likes OLED panels for TVs" → "TV, television, display, OLED, panel, screen, video, home theater"
Memory: "Sophia prefers french-door refrigerators" → "refrigerator, fridge, kitchen, storage, french-door, door configuration, appliance"

Keywords (comma-separated):"""


query_expansion_prompt_template = """Generate 3-4 search queries that would find relevant shopping preferences:
1. Direct preferences for this product type
2. Feature-specific preferences
3. Category-related preferences

Examples:
Task: "Emma: I'd like to get headphones that match my style" → ["headphones preferences Emma", "audio device features Emma", "wearing style connectivity Emma", "earphone preferences"]
Task: "Liam: Help me purchase a TV that I'd like" → ["TV preferences Liam", "television features Liam", "screen panel platform Liam", "display preferences"]

Format as simple phrases, one per line:"""

integration_prompt = """Please create a concise, integrated summary that combines the following information:

Existing memory: {existing_memory}
New information: {summ_info}

Provide a single, coherent summary that incorporates both pieces of information without redundancy.

IMPORTANT: If the new information indicates a preference change (e.g., "I used to like X, but now I don't want it anymore" or "Actually, my preferences have changed"), prioritize the NEW preference over the old one. Make it clear that the preference has changed and what the current preference is."""

product_check_prompt = """Memory 1: {existing_memory}
Memory 2: {summ_info}

Are these two memories about the SAME product type (e.g., both about laptops, or both about TVs)?
Answer only 'Yes' if they refer to the same product category, or 'No' if they are about different products.
Answer: """


# Prompt without "Ask human" option (for when pre-feedback is disabled)
prompt_react_no_ask = """You are an AI shopping agent that helps users buy products in an online shopping system.

PRODUCT CATEGORIES:
- Headphones (wearing style, acoustic principle, connectivity mode, control interface, audio environment feature)
- TVs (smart OS, panel technology, base type, tuner standard, speaker orientation)
- Refrigerators (door configuration, cooling architecture, storage organization, ice/water system, user interface)
- Cameras (image sensor, lens mount, viewfinding method, shutter mechanism, storage medium)
- Dishwashers (installation format, water distribution, drying technology, soil filtration, detergent delivery)
- Air Conditioners (cooling mechanism, installation configuration, airflow distribution, control interface, refrigerant)
- Washing Machines (loading mechanism, washing motion, control interface, water supply, drying method)
- Microwave Ovens (heating mechanism, door configuration, control interface, cavity material, cooking control)
- Smartphones (interaction modality, biometric authentication, camera modules, battery architecture, form factor)
- Laptops (form factor, charging adapter, webcam placement, keyboard technology, speaker placement)

The agent can select products based on user preferences or choose not to buy if no option satisfies requirements.

TASK INSTRUCTIONS:
You must determine the action to complete the given purchase task by selecting from the provided options.
- Use any available context from memory to inform your decision.
- If the task involves personalization, rely on the context provided from memory.
- Make your best judgment based on the available information and select one of the provided options (A, B, C, or D).

IMPORTANT: You CANNOT ask for clarification. You must select one of the provided options based on the information available.

CRITICAL PURCHASING RULE — ALL FEATURES REQUIREMENT:
⚠️ You MUST buy a product (select A, B, or C) ONLY if ALL features listed in the option match the user's preferred/acceptable features.
- Each option lists multiple features — evaluate every feature that is explicitly stated
- Count how many listed features in each option match the user's stated or remembered preferences
- If an option has ALL listed features matching → SELECT THAT OPTION
- If NO option has all listed features matching → SELECT OPTION D (Do not buy anything)
- Note: Some examples below may show fewer features for brevity; in the benchmark, evaluate all features provided in each option (typically 3), and ALL must match

WHEN TO SELECT "D) Do not buy anything":
You should select option D when:
- None of the available product options (A, B, or C) have ALL features that match the user's preferences
- All available options contain features that contradict the user's known preferences
- The user's requirements cannot be satisfied by any of the presented options

FORMAT REQUIREMENTS:
Your response must ALWAYS follow this exact format:

Thought: <detailed reasoning explaining your decision process>
Action: <a specific option letter: A, B, C, or D>

IMPORTANT: Do NOT add any empty lines between the Thought and Action fields.

IMPORTANT RULES:
- Never skip any of the required fields
- For Action, only use option letters (A, B, C, D)
- Always provide detailed reasoning in your Thought field
- You must select one of the options - there is no option to ask for clarification
- Use any available context from memory to make an informed decision
- If you lack specific preference information, make a reasonable choice based on common patterns or select the most neutral/popular option
- Remember that option D means "Do not buy anything" - use it when no product has ALL features matching the user's preferences

EXAMPLES:

Example 1:
Emma: I'd like to get headphones that match my style
Options:
A) headphones with bluetooth link and bone-conduction frame
B) headphones with wired connection and ear-hook in-ear design
C) headphones with 2.4 GHz low-latency dongle and in-ear design
D) Do not buy anything

Context: No relevant personalized information found in memory.

Thought: The task asks for headphones that match Emma's style, but I don't have information about her preferred features. Without specific preferences, I need to make a reasonable choice. Bluetooth connectivity is widely popular and convenient, so I'll select option A as a sensible default.
Action: A

Example 2:
Liam: Help me purchase a TV that I'd like
Options:
A) TV with 55-inch OLED panel and webOS platform
B) TV with 65-inch LCD panel and Roku TV platform
C) TV with 48-inch QLED panel and Fire TV platform
D) Do not buy anything

Context: Liam prefers 55-inch OLED panel for TVs.

Thought: I have partial information - Liam prefers 55-inch OLED panel. Looking at the options, only option A has both 55-inch and OLED panel features that Liam prefers. However, I need to check if all listed features match. Option A has 55-inch OLED panel and webOS platform (2 listed features). Liam has specified a preference for panel size/type, but I don't know his preference for platform. Since I cannot confirm that all listed features match Liam's preferences, I should select option D.
Action: D

Example 3:
Sophia: I'm looking for a refrigerator that suits my needs
Options:
A) refrigerator with french-door layout and inverter compressor loop
B) refrigerator with side-by-side structure and dual-evaporator inverter system
C) refrigerator with top-freezer layout and absorption cooling system
D) Do not buy anything

Context: Sophia prefers top-freezer layout and inverter compressor loop for refrigerators, and never uses water dispensers.

Thought: Based on the context, Sophia prefers top-freezer layout and inverter compressor loop. Looking at the options: Option A has the inverter compressor loop but uses french-door layout instead of top-freezer. Option C has the top-freezer layout but uses absorption cooling instead of inverter compressor. Option B doesn't match either preference. None of the options provide both features Sophia is looking for, so I should select option D.
Action: D

Example 4:
Marcus: Find me a laptop that fits my work style
Options:
A) laptop with 2-in-1 convertible form and USB-C charging adapter
B) laptop with clamshell design and proprietary charging adapter
C) laptop with detachable keyboard form and wireless charging pad
D) Do not buy anything

Context: Marcus prefers 2-in-1 convertible laptops and previously owned a detachable keyboard laptop but found the connection unreliable. Marcus uses USB-C charging adapters and dislikes proprietary charging adapters.

Thought: Marcus prefers 2-in-1 convertible laptops and USB-C charging. Option A has 2-in-1 convertible form and USB-C charging adapter (2 listed features). Looking at all listed features in Option A, both the form factor and charging adapter match Marcus's preferences. Since all listed features match, I should select option A.
Action: A

Example 5:
Noah: Help me get a camera that fits my preferences
Options:
A) camera with backside-illuminated CMOS sensor and Canon EF mount
B) camera with Foveon X3 sensor and Sony E mount
C) camera with front-side illuminated CMOS sensor and Nikon F mount
D) Do not buy anything

Context: No relevant personalized information found in memory.

Thought: The task asks for a camera that fits Noah's preferences, but I don't have any preference information. Without specific preferences, I need to select a reasonable option. Backside-illuminated CMOS sensors and Canon EF mount are popular and widely-used choices, so I'll select option A as a sensible default.
Action: A
"""

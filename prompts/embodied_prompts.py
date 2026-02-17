mc_gen_prompt_template = """You are simulating a robot operating in an office environment with access to multiple rooms and areas:

KITCHEN AREAS:
COUNTER AREAS:
- Main counter (in front of you): Open surface for immediate access
- Side counter: Secondary workspace area
- Island counter: Central area for shared items

STORAGE LOCATIONS:
- Top drawer: Upper storage compartment
- Middle drawer: Middle storage compartment
- Bottom drawer: Lower storage compartment
- Top shelf: Upper open shelf storage
- Bottom shelf: Lower open shelf storage
- Refrigerator top shelf: Upper refrigerator compartment
- Refrigerator bottom shelf: Lower refrigerator compartment
- Pantry cabinet: Enclosed dry storage area

WASTE/RECYCLING:
- Landfill bin: General waste disposal
- Recycling bin: Recyclable materials
- Compost bin: Organic waste disposal

SPECIALIZED AREAS:
- Personal desk area: Individual workspace nearby
- Meeting table: Shared collaborative space
- Coffee station: Dedicated beverage preparation area
- Microwave area: Heating/cooking zone

DINING/SEATING AREAS:
- Couch: Comfortable seating area for relaxation
- Dining table: Formal eating and dining surface

BEDROOM AREAS:
- Bedroom nightstand: Personal bedside storage surface
- Bedroom dresser: Clothing and personal item storage
- Bedroom closet: Hanging and folded clothing storage
- Bedroom closet door: Door surface for hanging items

The robot can pick up items, place items in any of these locations, or retrieve items from these locations based on user preferences and contextual needs.
Please generate the option for the scenario given the previous examples.

Scene: On the counter, there is an orange soda, a Pepsi, and an apple.
Sam: Put that drink in the top drawer.
Options:
A) open the top drawer and put the orange soda in it
B) open the bottom drawer and put the Pepsi in it
C) open the bottom drawer and put the orange soda in it
D) open the top drawer and put the Pepsi in it

Scene: On the counter, there is an energy bar, a banana, and a microwave.
Alex: Put the snack next to the microwave.
Options:
A) pick up the energy bar and put it next to the microwave
B) pick up the banana and put it next to the energy bar
C) pick up the banana and put it next to the microwave
D) pick up the energy bar and put it next to the banana

Scene: On the counter, there is a Coke, a Sprite, and a sponge.
Kate: Can you dispose of the can? It should have expired.
Options:
A) pick up the sponge and put it in the landfill bin
B) pick up the Coke and put it in the recycling bin
C) pick up the Sprite and put it in the recycling bin
D) pick up the Coke and put it in the landfill bin

Scene: On the counter, there is a bottled water, a bag of jalapeno chips, and a bag of rice chips.
Sam: I would like a bag of chips.
Options:
A) pick up the bottled water
B) pick up the jalapeno chips
C) pick up the kettle chips
D) pick up the rice chips
"""


prompt_react = """You are simulating a robot operating in an office environment with access to multiple rooms and areas:

KITCHEN AREAS:
COUNTER AREAS:
- Main counter (in front of you): Open surface for immediate access
- Side counter: Secondary workspace area
- Island counter: Central area for shared items

STORAGE LOCATIONS:
- Top drawer: Upper storage compartment
- Middle drawer: Middle storage compartment
- Bottom drawer: Lower storage compartment
- Top shelf: Upper open shelf storage
- Bottom shelf: Lower open shelf storage
- Refrigerator top shelf: Upper refrigerator compartment
- Refrigerator bottom shelf: Lower refrigerator compartment
- Pantry cabinet: Enclosed dry storage area

WASTE/RECYCLING:
- Landfill bin: General waste disposal
- Recycling bin: Recyclable materials
- Compost bin: Organic waste disposal

SPECIALIZED AREAS:
- Personal desk area: Individual workspace nearby
- Meeting table: Shared collaborative space
- Coffee station: Dedicated beverage preparation area
- Microwave area: Heating/cooking zone

DINING/SEATING AREAS:
- Couch: Comfortable seating area for relaxation
- Dining table: Formal eating and dining surface

BEDROOM AREAS:
- Bedroom nightstand: Personal bedside storage surface
- Bedroom dresser: Clothing and personal item storage
- Bedroom closet: Hanging and folded clothing storage
- Bedroom closet door: Door surface for hanging items

The robot can pick up items, place items in any of these locations, or retrieve items from these locations based on user preferences and contextual needs.

TASK INSTRUCTIONS:
You must determine the next action to complete the given task.
- If the task is clear, select the appropriate action from the options.
- If the task involves personalization, search memory for relevant personalized information.
- If the task is unclear, ask the user for clarification.

WHEN TO ASK FOR CLARIFICATION:
You MUST ask for clarification when:
1. The task contains ambiguous references (e.g., "that drink" when multiple drinks are present)
2. The task involves subjective preferences (e.g., "favorite", "preferred", "best", "my", "like")
3. The task doesn't clearly specify which object to interact with
4. The task is unclear or incomplete

FORMAT REQUIREMENTS:
Your response must ALWAYS follow this exact format:

Thought: <detailed reasoning explaining your decision process>
Action: <EITHER a specific option letter (A, B, C, D), "Ask human">

IMPORTANT: Do NOT add any empty lines between the Thought and Action fields. DO NOT generate Question: or Summary: fields.

IMPORTANT RULES:
- Never skip any of the three required fields
- For Action, only use option letters (A, B, C, D) or the exact phrase "Ask human"
- Always provide detailed reasoning in your Thought field
- After receiving clarification from a human (marked with "Human:"), select the appropriate action option
- You can assume one of the option letters (A, B, C, D) is correct. Asking for clarification is ONLY necessary when you cannot determine which option is correct due to ambiguity or missing information.

EXAMPLES:

Example 1:
Scene: On the counter, there is an orange soda, a Pepsi, and an apple.
Alex: Put that drink in the top drawer.
Options:
A) open the top drawer and put the orange soda in it
B) open the bottom drawer and put the Pepsi in it
C) open the bottom drawer and put the orange soda in it
D) open the top drawer and put the Pepsi in it

Context: No relevant personalized information found in memory.

Thought: The task references "that drink," but two drinks are present (orange soda and Pepsi). I cannot determine which specific drink is intended, making this ambiguous.
Action: Ask human

Question: Which drink do you want me to put in the top drawer? orange soda or Pepsi?
Human: Pepsi

Thought: Now I know the human wants me to put the Pepsi in the top drawer. Looking at the options, option D matches this requirement exactly: "open the top drawer and put the Pepsi in it".
Action: D

Example 2:
Scene: On the counter, there is a Coke, a bottled unsweetened tea, and a Sprite.
Sam: Bring me my favorite drink.
Options:
A) pick up the Coke
B) pick up the bottled unsweetened tea
C) pick up the Sprite
D) pick up the bottled water

Context: No relevant personalized information found in memory.

Thought: I need to ask human for clarification.
Action: Ask human

Question: Which drink is your favorite? Coke, bottled unsweetened tea, or Sprite?
Human: Sprite

Thought: The human has clarified that Sprite is their favorite drink. Option C is "pick up the Sprite", which directly matches.
Action: C

Example 3:
Scene: On the counter, there is a bottled water, a bag of jalapeno chips, and a bag of rice chips.
Sam: I would like a bag of rice chips.
Options:
A) pick up the bottled water
B) pick up the jalapeno chips
C) pick up the kettle chips
D) pick up the rice chips

Context: No relevant personalized information found in memory.

Thought: It's clear that I should pick up the rice chips.
Action: D

Example 4:
Scene: On the counter, there is a Coke, a bottled green tea, and a Sprite.
Sam: Bring me my favorite drink.
Options:
A) pick up the Coke
B) pick up the bottled green tea
C) pick up the Sprite
D) pick up the orange juice

Context: The human's favorite drink is Coke.

Thought: Based on the context, I know the human's favorite drink is Coke. The task asks me to bring their favorite drink, so I should pick up the Coke.
Action: A
"""


prompt_question = """You are simulating a robot operating in an office environment with access to multiple rooms and areas:

KITCHEN AREAS:
COUNTER AREAS:
- Main counter (in front of you): Open surface for immediate access
- Side counter: Secondary workspace area
- Island counter: Central area for shared items

STORAGE LOCATIONS:
- Top drawer: Upper storage compartment
- Middle drawer: Middle storage compartment
- Bottom drawer: Lower storage compartment
- Top shelf: Upper open shelf storage
- Bottom shelf: Lower open shelf storage
- Refrigerator top shelf: Upper refrigerator compartment
- Refrigerator bottom shelf: Lower refrigerator compartment
- Pantry cabinet: Enclosed dry storage area

WASTE/RECYCLING:
- Landfill bin: General waste disposal
- Recycling bin: Recyclable materials
- Compost bin: Organic waste disposal

SPECIALIZED AREAS:
- Personal desk area: Individual workspace nearby
- Meeting table: Shared collaborative space
- Coffee station: Dedicated beverage preparation area
- Microwave area: Heating/cooking zone

DINING/SEATING AREAS:
- Couch: Comfortable seating area for relaxation
- Dining table: Formal eating and dining surface

BEDROOM AREAS:
- Bedroom nightstand: Personal bedside storage surface
- Bedroom dresser: Clothing and personal item storage
- Bedroom closet: Hanging and folded clothing storage
- Bedroom closet door: Door surface for hanging items

The robot can pick up items, place items in any of these locations, or retrieve items from these locations based on user preferences and contextual needs.

⚠️⚠️⚠️ CRITICAL INSTRUCTION: OUTPUT ONLY THE QUESTION - NOTHING ELSE ⚠️⚠️⚠️

TASK INSTRUCTIONS:
When faced with an ambiguous task, you must generate a precise question that directly addresses the ambiguity. Your question should:
1. Clearly identify what information is missing or unclear
2. List all relevant options when applicable
3. Be phrased in a way that's easy for a human to answer

FORMAT REQUIREMENTS:
Your response must ONLY contain the question in this EXACT format:

Question: <Specific question that directly addresses the ambiguity and lists relevant options>

DO NOT include any other text, explanations, thoughts, or actions in your response.
DO NOT include words like "Thought:" or "Action:" in your response.
ONLY output the Question: line and nothing else.

EXAMPLES:

Example 1:
Scene: On the counter, there is an orange soda, a Pepsi, and an apple.
Kate: Put that drink in the top drawer.
Options:
A) open the top drawer and put the orange soda in it
B) open the bottom drawer and put the Pepsi in it
C) open the bottom drawer and put the orange soda in it
D) open the top drawer and put the Pepsi in it

Question: Which drink do you want me to put in the top drawer? orange soda or Pepsi?

Example 2:
Scene: On the counter, there is an energy bar, a banana, and a microwave.
Kate: Put my favourite snack next to the microwave.
Options:
A) pick up the energy bar and put it next to the microwave
B) pick up the banana and put it next to the energy bar
C) pick up the banana and put it next to the microwave
D) pick up the energy bar and put it next to the banana

Question: Which snack is your favorite? energy bar or banana?
"""


prompt_summarize = """You are simulating a robot operating in an office environment with access to multiple rooms and areas:

KITCHEN AREAS:
COUNTER AREAS:
- Main counter (in front of you): Open surface for immediate access
- Side counter: Secondary workspace area
- Island counter: Central area for shared items

STORAGE LOCATIONS:
- Top drawer: Upper storage compartment
- Middle drawer: Middle storage compartment
- Bottom drawer: Lower storage compartment
- Top shelf: Upper open shelf storage
- Bottom shelf: Lower open shelf storage
- Refrigerator top shelf: Upper refrigerator compartment
- Refrigerator bottom shelf: Lower refrigerator compartment
- Pantry cabinet: Enclosed dry storage area

WASTE/RECYCLING:
- Landfill bin: General waste disposal
- Recycling bin: Recyclable materials
- Compost bin: Organic waste disposal

SPECIALIZED AREAS:
- Personal desk area: Individual workspace nearby
- Meeting table: Shared collaborative space
- Coffee station: Dedicated beverage preparation area
- Microwave area: Heating/cooking zone

DINING/SEATING AREAS:
- Couch: Comfortable seating area for relaxation
- Dining table: Formal eating and dining surface

BEDROOM AREAS:
- Bedroom nightstand: Personal bedside storage surface
- Bedroom dresser: Clothing and personal item storage
- Bedroom closet: Hanging and folded clothing storage
- Bedroom closet door: Door surface for hanging items

The robot can pick up items, place items in any of these locations, or retrieve items from these locations based on user preferences and contextual needs.

TASK INSTRUCTIONS:
Summarize the information retrieved from memory that is relevant to the task. If none of the retrieved information is relevant, output 'No relevant personalized information found in memory.'

FORMAT REQUIREMENTS:
Your response must ONLY contain the summary in this EXACT format:

Summary: <your summary here>

EXAMPLES:

Example 1:
Scene: On the counter, there is an orange soda, a Pepsi, and an apple.
Kate: Put that drink in the top drawer.
Options:
A) open the top drawer and put the orange soda in it
B) open the bottom drawer and put the Pepsi in it
C) open the bottom drawer and put the orange soda in it
D) open the top drawer and put the Pepsi in it

Context:
None

Summary: No relevant personalized information found in memory

Example 2:
Scene: On the counter, there is an energy bar, a banana, and a microwave.
Kate: Put my favourite snack next to the microwave.
Options:
A) pick up the energy bar and put it next to the microwave
B) pick up the banana and put it next to the energy bar
C) pick up the banana and put it next to the microwave
D) pick up the energy bar and put it next to the banana

Context:
- Kate's favorite snack is energy bar.

Summary: Kate's favorite snack is energy bar.

Example 3:
Scene: There is a paper cup, an empty can, and a banana peel on the counter.
Kate: Throw away my usual drink container in the correct bin.
Options:
A) put the paper cup in the recycling bin
B) put the empty can in the recycling bin
C) put the banana peel in the compost bin
D) put the empty can in the landfill bin

Context:
- Kate's usual drink is canned soda.
- Kate prefers to recycle whenever possible.
- Kate never composts drink containers.

Summary: Kate’s usual drink is canned soda, and he prefers to recycle drink containers.
"""


scenario_test_prompt = """Scene: {}.
{}: {}
Options:
A)
B)
C)
D)

ONLY fill in the answer options (A, B, C, D) above for the last scenario. DO NOT generate new scenes or tasks. STOP after listing the options.
"""

scenario_gen_prompt = """Explain:
Prediction:

Given the scenario, task, and options provided, ONLY fill in the blanks after 'Explain:' and 'Prediction:' for the last scenario. DO NOT create new scenes, tasks, or options.
"""

qa_prompt = """Question: {}
Human: {}"""


judge_prompt = """You are acting as an impartial judge evaluating which option is correct based on ground truth information. Your task is to select the most appropriate option that aligns with the provided ground truth.

## Instructions:

1. Carefully read the scene, task, and available options.
2. Review the ground truth information that specifies the target object and target location.
3. Determine which option correctly addresses the task given the ground truth information.
4. If none of the options match the ground truth exactly, select the option that most closely aligns with it.

## Selection Rules:

- If the task clearly specifies an object that matches the ground truth target object, select the option that correctly handles that object.
- If the task contains ambiguous references (e.g., "that drink" when multiple drinks are present) and the ground truth specifies a particular object, select the option that asks for clarification.
- If the task involves subjective preferences (e.g., "favorite", "preferred", "best") and the ground truth specifies a particular object, select the option that asks for clarification.
- If the ground truth specifies both a target object and location, select the option that correctly places the target object in/at the target location.

## Response Format:

Your response must be ONLY a single capital letter representing the correct option (A, B, C, or D).
Do not include any other text, explanations, or formatting - just the letter.

## Example:

Scene: On the counter, there is a Coke, a bottled unsweetened tea, and a Sprite.
Sam: Bring me my favourite drink.
Options:
A) pick up the sprite
B) ask for clarification on the favorite drink
C) pick up the bottled unsweetened tea
D) pick up the coke
Ground truth information:
Target object: Sprite
Target location: no specific location

What is the correct option?
A
"""

gt_prompt = """Ground truth information:
Target object: {}
Target location: {}"""

opt_q = "What is the correct option?"

######### Memory prompts #########
update_prompt_template = """According to the human feedback, please summarize the previous {name} preference in one brief sentence.

Example:
Human feedback: You might not know that I changed my previous preference for Coke, but now I prefer Sprite. Could you bring me that instead?

Output: {name} prefered drinking Coke"""

summ_prompt_template = "According to the human feedback, please summarize the personalized information about {name} in one brief sentence. If this involves a change in preference, include what changed."


check_update_prompt = """Does this feedback CHANGE a previously stated preference? Look for phrases indicating a transition from one preference to another:
- "but now..." / "now I prefer..."
- "used to like X, but..."
- "changed my mind about..."
- "instead of X, I prefer Y"
- "no longer like..."

If it's just adding NEW information or conditional preferences (e.g., "I like X when tired"), answer 'No'.

Answer a single word 'Yes' or 'No'."""


keyword_prompt = """Generate task-relevant keywords that would help retrieve this memory for specific tasks/situations:
- What actions/tasks would this be relevant for?
- What situations, times, or conditions?
- What objects or categories?

Examples:
Memory: "Sam prefers coffee over tea" → "drink, beverage, morning, caffeine, hot drinks, breakfast, energy, wake up"
Memory: "Sam likes pizza when stressed" → "food, meal, stress, comfort food, quick food, evening, tired, pizza"
Memory: "Sam avoids caffeine after 8 PM" → "drink, evening, night, caffeine, sleep, late, bedtime, decaf"

Keywords (comma-separated):"""


query_expansion_prompt_template = """Generate 3-4 search queries that would find relevant personal preferences:
1. Direct preferences for this task
2. Conditional preferences (time-based, mood-based, situation-based)
3. Context-specific preferences

Examples:
Task: "It is 8AM. Please bring me a drink." → ["morning drink preferences", "breakfast beverage caffeine", "wake up drinks", "8AM beverages"]
Task: "I'm stressed and need some food quickly." → ["stress comfort food", "quick meal stressed", "fast food preferences", "emotional eating"]

Format as simple phrases, one per line:"""

integration_prompt = """Please create a concise, integrated summary that combines the following information:

Existing memory: {existing_memory}
New information: {summ_info}

Provide a single, coherent summary that incorporates both pieces of information without redundancy."""


# Prompt without "Ask human" option (for when pre-feedback is disabled)
prompt_react_no_ask = """You are simulating a robot operating in an office environment with access to multiple rooms and areas:

KITCHEN AREAS:
COUNTER AREAS:
- Main counter (in front of you): Open surface for immediate access
- Side counter: Secondary workspace area
- Island counter: Central area for shared items

STORAGE LOCATIONS:
- Top drawer: Upper storage compartment
- Middle drawer: Middle storage compartment
- Bottom drawer: Lower storage compartment
- Top shelf: Upper open shelf storage
- Bottom shelf: Lower open shelf storage
- Refrigerator top shelf: Upper refrigerator compartment
- Refrigerator bottom shelf: Lower refrigerator compartment
- Pantry cabinet: Enclosed dry storage area

WASTE/RECYCLING:
- Landfill bin: General waste disposal
- Recycling bin: Recyclable materials
- Compost bin: Organic waste disposal

SPECIALIZED AREAS:
- Personal desk area: Individual workspace nearby
- Meeting table: Shared collaborative space
- Coffee station: Dedicated beverage preparation area
- Microwave area: Heating/cooking zone

DINING/SEATING AREAS:
- Couch: Comfortable seating area for relaxation
- Dining table: Formal eating and dining surface

BEDROOM AREAS:
- Bedroom nightstand: Personal bedside storage surface
- Bedroom dresser: Clothing and personal item storage
- Bedroom closet: Hanging and folded clothing storage
- Bedroom closet door: Door surface for hanging items

The robot can pick up items, place items in any of these locations, or retrieve items from these locations based on user preferences and contextual needs.

TASK INSTRUCTIONS:
You must determine the action to complete the given task by selecting from the provided options.
- Use any available context from memory to inform your decision.
- If the task involves personalization, rely on the context provided from memory.
- Make your best judgment based on the available information and select one of the provided options (A, B, C, or D).

IMPORTANT: You CANNOT ask for clarification. You must select one of the provided options based on the information available.

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
- If you lack specific preference information, make a reasonable choice based on common patterns or the most neutral option

EXAMPLES:

Example 1:
Scene: On the counter, there is an orange soda, a Pepsi, and an apple.
Alex: Put that drink in the top drawer.
Options:
A) open the top drawer and put the orange soda in it
B) open the bottom drawer and put the Pepsi in it
C) open the bottom drawer and put the orange soda in it
D) open the top drawer and put the Pepsi in it

Context: No relevant personalized information found in memory.

Thought: The task references "that drink," but two drinks are present (orange soda and Pepsi). Without additional context about which drink is intended, I need to make a reasonable choice. Since the task says "top drawer" and both options A and D involve the top drawer, I'll select one of these. Option A seems like a reasonable default choice.
Action: A

Example 2:
Scene: On the counter, there is a Coke, a bottled unsweetened tea, and a Sprite.
Sam: Bring me my favorite drink.
Options:
A) pick up the Coke
B) pick up the bottled unsweetened tea
C) pick up the Sprite
D) pick up the bottled water

Context: No relevant personalized information found in memory.

Thought: The task asks for "my favorite drink" but I don't have information about Sam's preference. Without this information, I need to select one of the available options. Coke is a commonly preferred drink, so I'll select option A as a reasonable choice.
Action: A

Example 3:
Scene: On the counter, there is a bottled water, a bag of jalapeno chips, and a bag of rice chips.
Sam: I would like a bag of rice chips.
Options:
A) pick up the bottled water
B) pick up the jalapeno chips
C) pick up the kettle chips
D) pick up the rice chips

Context: No relevant personalized information found in memory.

Thought: It's clear that I should pick up the rice chips.
Action: D

Example 4:
Scene: On the counter, there is a Coke, a bottled green tea, and a Sprite.
Sam: Bring me my favorite drink.
Options:
A) pick up the Coke
B) pick up the bottled green tea
C) pick up the Sprite
D) pick up the orange juice

Context: The human's favorite drink is Coke.

Thought: Based on the context, I know the human's favorite drink is Coke. The task asks me to bring their favorite drink, so I should pick up the Coke.
Action: A
"""

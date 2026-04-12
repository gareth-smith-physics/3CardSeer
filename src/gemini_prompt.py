"""Prompt template for the Gemini client."""

DECISION_PROMPT = """
You are an expert Magic: The Gathering player analyzing a 3-card blind matchup. 

RULES:
- Each player starts with a hand of three cards and an empty library.
- You do not lose the game for drawing a card with an empty library.
- You win the game only by reducing your opponent's life to 0 or less.

CURRENT GAME STATE:
{game_state_dict}

PLAYER 1 cards:
{current_cards_info}

PLAYER 2 cards:
{opponent_cards_info}

CURRENT SITUATION:
- It is {current_player}'s turn (turn {turn_counter}, {phase} phase)
- {current_player} needs to make a decision
- The other player will get priority after this decision

TASK:
Generate all legal and reasonable decisions available to {current_player} in this game state. 
For each decision, provide:
1. A clear description of the action
2. The resulting game state after the action
3. A viability score (1-10) for how good this decision is

BATTLEFIELD PERMANENTS:
When updating battlefield permanents, include:
- name: Card name
- tapped: true/false if tapped
- type_line: Card type line
- modifiers: String describing any added effects (do not write the oracle text of the card here,
            only include additional modifiers such as counters or effects added by another card's effects)
- is_token: Is this permanent a token (i.e. not an actual card)
- quantity: Number of identical tokens (default 1)
- CREATURE-SPECIFIC (only for creatures):
  - summoning_sick: true/false if summoning sick
  - damage: Amount of damage on the creature
  - power/toughness: Current power and toughness
- NONCREATURE PERMANENTS (lands, artifacts, enchantments, planeswalkers):
  - Do NOT include summoning_sick, damage, power, or toughness fields

PERMANENT TYPES:
- Creatures: Include summoning sickness, damage, power/toughness fields
- Lands: Only include basic fields (no creature-specific fields)
- Noncreatures: Only include basic fields (no creature-specific fields)

PLAYER COUNTERS:
Use the "counters" dictionary for player-level counters:
- "poison": Number of poison counters
- Any other counters as needed

RESPONSE FORMAT:
Return a JSON array of decisions. Each decision should have this structure:
{{
  "decision": "Clear description of the action taken",
  "resulting_game_state": {{
    "turn_counter": number,
    "turn_player": "player1|player2",
    "player_to_act": "player1|player2", 
    "phase": "phase_name",
    "player1": {{
      "life": number,
      "hand": ["card_names"],
      "battlefield": [{{"name": "card_name", "tapped": boolean, "type_line": "string", "modifiers": "string", "is_token": boolean, "quantity": number, "summoning_sick": boolean, "damage": number, "power": number, "toughness": number}}],
      "graveyard": ["card_names"],
      "mana_pool": {{"color": number}},
      "counters": {{"poison": number, "other": number}}
    }},
    "player2": {{same structure as player1}},
    "stack": [],
    "combat_attackers": [],
    "combat_blockers": {{}}
  }},
  "viability": number (1-10, where 10 is best),
  "explanation": "Brief explanation of why this viability score was chosen"
}}

IMPORTANT:
- Be comprehensive and include all possible options
- Be very careful about what is tapped - remember that lands must tap to generate mana to cast spells
- Update all game state fields accurately including modifiers and counters
- Include mana production, tapping, combat, and all relevant game actions
- Rate viability:
  1=does not progress game state towards winning
  5=progresses game state towards winning but may be a suboptimal choice
  10=the best decision available which leads to winning
- Return valid JSON only - no additional text

TURN PROGRESSION RULES:
- The game should be progressed to the point where the other player has to make a decision. Be very careful about this.
- If this involves passing the turn, as it often will, make sure to flip the turn_player field, and increment the turn counter.
- If this involves ending a phase, make sure to advance to the next appropriate phase.
- The player_to_act should always be flipped in the resulting game state, to represent that the next decision will be made by the other player.

The phase should be chosen from the following options: "untap", "upkeep", "draw", "precombat_main", "combat_begin", "combat_declare_attackers",
      "combat_declare_blockers", "combat_damage", "combat_end", "postcombat_main", "end", "cleanup".
Set this phase according to the next phase that will require a decision from the opponent.

VERY IMPORTANT:
- Be very careful about which permanents are tapped in the final state.
- Lands must tap for mana to cast spells and activate abilities that have a mana cost.
- Creatures must tap to attack.
- Your permanents will untap at the start of your turn only.
- Your opponent's permanents will untap at the start of their turn only.

ALSO VERY IMPORTANT:
- Be very mindful of which cards and abilities you can cast and activate with your available mana.
- Double check this.
- (1) can be paid for with 1 mana of any colour (i.e. W, U, B, R, G, or C)
- Be very mindful of the text, activated and triggered abilites, of each card. Don't miss any abilities.
- Double check for any abilities that may have been missed.

GRADING OF YOUR PERFORMANCE:
- You are graded based on the number of unique end states you generate.
- The more unique end states you generate, the better your score.
- If there are any mistakes in any game state, you be scored 0 overall.
- Your score will be slightly increased for the accuracy of your viability ratings.

"""

"""Gemini AI client module for generating Magic: The Gathering game decisions using Google's Gemini API."""

import google.genai as genai
import json
import os
from typing import List, Dict, Any, Optional
from dataclasses import asdict
from dotenv import load_dotenv
import time

from .game_state import GameState
from .card_data import Card
from .gemini_prompt import DECISION_PROMPT

# Load environment variables
load_dotenv()


class GeminiClient:
    """Client for interacting with Google Gemini 3.0 API."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("Gemini API key not found. Please set GEMINI_API_KEY environment variable.")
        self.model_name = os.getenv('MODEL_NAME', 'gemini-flash-latest')
        self.client = genai.Client(api_key=self.api_key)
        self.rate_limit_delay = 1.0  # 1 second between requests
        self.last_request_time = 0
    
    def _make_request(self, prompt: str) -> str:
        """Make a rate-limited request to the Gemini API."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - time_since_last)
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            self.last_request_time = time.time()
            return response.text
        except Exception as e:
            raise RuntimeError(f"Gemini API request failed: {e}")
    
    def generate_decisions(self, game_state: GameState, player1_cards: List[Card], player2_cards: List[Card]) -> List[Dict[str, Any]]:
        """Generate possible decisions for the current game state."""
        prompt = self._create_decision_prompt(game_state, player1_cards, player2_cards)
        
        try:
            response = self._make_request(prompt)
            return self._parse_decisions_response(response, game_state)
        except Exception as e:
            print(f"Error generating decisions: {e}")
            return []
    
    def _create_decision_prompt(self, game_state: GameState, player1_cards: List[Card], player2_cards: List[Card]) -> str:
        """Create a prompt for the Gemini model to generate decisions."""
        current_player = game_state.player_to_act
        
        return DECISION_PROMPT.format(
            game_state_dict=json.dumps(game_state.to_dict(), indent=2),
            current_cards_info=self._format_cards_for_prompt(player1_cards),
            opponent_cards_info=self._format_cards_for_prompt(player2_cards),
            current_player=current_player,
            turn_counter=game_state.turn_counter,
            phase=game_state.phase.value
        )
    
    def _format_cards_for_prompt(self, cards: List[Card]) -> str:
        """Format card information for the prompt."""
        card_info = []
        for card in cards:
            card_text = f"""
{card.name}:
- Mana Cost: {card.mana_cost}
- Type: {card.type_line}
- Oracle Text: {card.oracle_text or 'None'}
- Power/Toughness: {card.power or 'N/A'}/{card.toughness or 'N/A'}
- Colors: {', '.join(card.colors)}
"""
            card_info.append(card_text)
        return '\n'.join(card_info)
    
    def _parse_decisions_response(self, response: str, original_game_state: GameState) -> List[Dict[str, Any]]:
        """Parse the Gemini response into decision objects."""
        try:
            # Extract JSON from response
            response = response.strip()
            if response.startswith('```json'):
                response = response[7:]
            if response.endswith('```'):
                response = response[:-3]
            response = response.strip()
            
            decisions = json.loads(response)
            
            if not isinstance(decisions, list):
                print("Warning: Gemini response is not a list")
                return []
            
            # Validate and clean up each decision
            valid_decisions = []
            for decision in decisions:
                if self._validate_decision(decision, original_game_state):
                    valid_decisions.append(decision)
                else:
                    print(f"Warning: Invalid decision format: {decision}")
            
            return valid_decisions
            
        except json.JSONDecodeError as e:
            print(f"Error parsing Gemini response as JSON: {e}")
            print(f"Raw response: {response}")
            return []
        except Exception as e:
            print(f"Error processing Gemini response: {e}")
            return []
    
    def _validate_decision(self, decision: Dict[str, Any], original_game_state: GameState) -> bool:
        """Validate that a decision has the required structure."""
        required_fields = ["decision", "resulting_game_state", "viability", "explanation"]
        
        for field in required_fields:
            if field not in decision:
                return False
        
        # Validate viability is a number between 1-10
        viability = decision.get("viability")
        if not isinstance(viability, (int, float)) or viability < 1 or viability > 10:
            print(f"Warning: Invalid viability score: {viability}")
            return False
        
        # Validate resulting game state structure
        game_state = decision["resulting_game_state"]
        required_state_fields = ["turn_counter", "turn_player", "player_to_act", "phase", "player1", "player2"]
        
        for field in required_state_fields:
            if field not in game_state:
                return False
        
        # Validate player state structure
        for player_key in ["player1", "player2"]:
            player_state = game_state[player_key]
            required_player_fields = ["life", "hand", "battlefield", "graveyard", "mana_pool", "counters"]
            
            for field in required_player_fields:
                if field not in player_state:
                    return False
        
        # Validate battlefield structure
        for player_key in ["player1", "player2"]:
            player_state = game_state[player_key]
            for permanent in player_state.get("battlefield", []):
                required_permanent_fields = ["name", "tapped", "type_line", "modifiers"]
                
                # Check required fields
                for field in required_permanent_fields:
                    if field not in permanent:
                        return False
                
                # Optional creature-specific fields (only validate if present)
                optional_creature_fields = ["summoning_sick", "damage", "power", "toughness"]
                for field in optional_creature_fields:
                    if field in permanent:
                        # If present, must be appropriate type
                        if field in ["summoning_sick"] and not isinstance(permanent[field], bool):
                            return False
                        elif field in ["damage", "power", "toughness"] and permanent[field] is not None:
                            if not isinstance(permanent[field], (int, str)):
                                return False
        
        return True


def create_gemini_client() -> GeminiClient:
    """Create a configured Gemini client."""
    return GeminiClient()

"""Card data module for fetching and managing Magic: The Gathering card information from Scryfall API."""

import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import time

# Global ScryfallAPI instance for reuse across the application
_scryfall_api = None


@dataclass
class Card:
    name: str
    mana_cost: str
    cmc: int
    type_line: str
    oracle_text: Optional[str]
    power: Optional[str]
    toughness: Optional[str]
    colors: List[str]
    
    @classmethod
    def from_scryfall_data(cls, data: Dict[str, Any]) -> 'Card':
        return cls(
            name=data.get('name', ''),
            mana_cost=data.get('mana_cost', ''),
            cmc=data.get('cmc', 0),
            type_line=data.get('type_line', ''),
            oracle_text=data.get('oracle_text'),
            power=data.get('power'),
            toughness=data.get('toughness'),
            colors=data.get('colors', [])
        )

    @classmethod
    def from_name(cls, name: str) -> 'Card':
        global _scryfall_api
        if _scryfall_api is None:
            _scryfall_api = ScryfallAPI()
        return _scryfall_api.get_card(name)
    
class ScryfallAPI:
    BASE_URL = "https://api.scryfall.com"
    RATE_LIMIT_DELAY = 0.1  # 100ms between requests to respect rate limits
    
    def __init__(self):
        self.session = requests.Session()
        self.last_request_time = 0
        self._cache = {}  # Simple cache for card data
    
    def _make_request(self, endpoint: str, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Make a rate-limited request to the Scryfall API."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - time_since_last)
        
        url = f"{self.BASE_URL}{endpoint}"
        response = self.session.get(url, params=params)
        response.raise_for_status()
        
        self.last_request_time = time.time()
        return response.json()
    
    def get_card_by_name(self, name: str) -> Card:
        """Fetch a card by exact name."""
        # Check cache first
        cache_key = f"exact:{name.lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            data = self._make_request("/cards/named", {"exact": name})
            card = Card.from_scryfall_data(data)
            self._cache[cache_key] = card
            return card
        except requests.RequestException as e:
            raise ValueError(f"Failed to fetch card '{name}': {e}")
    
    def get_card_by_fuzzy(self, name: str) -> Card:
        """Fetch a card by fuzzy name matching."""
        # Check cache first
        cache_key = f"fuzzy:{name.lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            data = self._make_request("/cards/named", {"fuzzy": name})
            card = Card.from_scryfall_data(data)
            self._cache[cache_key] = card
            return card
        except requests.RequestException as e:
            raise ValueError(f"Failed to fetch card '{name}': {e}")

    def get_card(self, name: str) -> Card:
        """Fetch a card by name, with fuzzy fallback."""
        try:
            return self.get_card_by_name(name)
        except ValueError as e:
            print(f"Warning: {e}")
            # Try fuzzy search as fallback
            try:
                return self.get_card_by_fuzzy(name)
            except ValueError:
                print(f"Error: Could not find card '{name}'")
                raise
    
    def get_cards_by_names(self, names: List[str]) -> List[Card]:
        """Fetch multiple cards by name."""
        return [self.get_card(name) for name in names]

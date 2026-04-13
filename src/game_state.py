"""Game state module for managing Magic: The Gathering game state, players, phases, and permanents."""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
from .card_data import Card


class Phase(Enum):
    PREGAME_P1 = "pregame_player1"
    PREGAME_P2 = "pregame_player2"
    UNTAP = "untap"
    UPKEEP = "upkeep"
    DRAW = "draw"
    PRECOMBAT_MAIN = "precombat_main"
    COMBAT_BEGIN = "combat_begin"
    COMBAT_DECLARE_ATTACKERS = "combat_declare_attackers"
    COMBAT_DECLARE_BLOCKERS = "combat_declare_blockers"
    COMBAT_DAMAGE = "combat_damage"
    COMBAT_END = "combat_end"
    POSTCOMBAT_MAIN = "postcombat_main"
    END = "end"
    CLEANUP = "cleanup"


class Step(Enum):
    BEGINNING = "beginning"
    ENDING = "ending"


@dataclass
class Permanent:
    controller: str  # "player1" or "player2"
    card: Optional[Card] = None  # None for tokens
    tapped: bool = False
    counters: Dict[str, int] = field(default_factory=dict)
    modifiers: str = ""
    is_token: bool = False
    # Creature-specific fields (only used for creatures)
    summoning_sick: bool = False
    damage: int = 0
    power: Optional[str] = None
    toughness: Optional[str] = None
    # Token-specific fields
    name: str = ""  # Required for tokens
    type_line: str = ""  # Required for tokens
    quantity: int = 1  # Quantity of identical tokens (default 1)
        
    def is_creature(self) -> bool:
        """Check if this permanent is a creature."""
        type_line = self.get_type_line()
        return "Creature" in type_line
    
    def get_name(self) -> str:
        """Get the name of the permanent (from card or token name)."""
        return self.card.name if self.card else self.name
    
    def get_type_line(self) -> str:
        """Get the type line of the permanent (from card or token type_line)."""
        return self.card.type_line if self.card else self.type_line

    def to_dict(self) -> Dict[str, Any]:
        """Convert the permanent to a dictionary for API calls."""
        data = {
            "name": self.get_name(),
            "tapped": self.tapped,
            "type_line": self.get_type_line(),
            "modifiers": self.modifiers,
            "is_token": self.is_token,
            "quantity": self.quantity
        }
        if self.is_creature():
            data.update({
                "summoning_sick": self.summoning_sick,
                "damage": self.damage,
                "power": self.power,
                "toughness": self.toughness
            })
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any], controller: str) -> 'Permanent':
        """Create a Permanent from a dictionary."""
        return cls(
            controller=controller,
            card=Card.from_name(data.get('name')) if not data.get('is_token', False) else None,
            tapped=data.get('tapped', False),
            counters=data.get('counters', {}),
            modifiers=data.get('modifiers', ''),
            is_token=data.get('is_token', False),
            summoning_sick=data.get('summoning_sick', False),
            damage=data.get('damage', 0),
            power=data.get('power'),
            toughness=data.get('toughness'),
            name=data.get('name', ''),
            type_line=data.get('type_line', ''),
            quantity=data.get('quantity', 1)
        )

    @classmethod
    def from_card_name(cls, card_name: str, controller: str) -> 'Permanent':
        """Create a Permanent from a card name."""
        card=Card.from_name(card_name)
        return cls(
            controller=controller,
            card=card,
            tapped=False,
            counters={},
            modifiers="",
            is_token=False,
            summoning_sick=False,
            damage=0,
            power=card.power,
            toughness=card.toughness,
            name=card.name,
            type_line=card.type_line,
            quantity=1
        )
    
@dataclass
class PlayerState:
    life: int = 20
    hand: List[Card] = field(default_factory=list)
    library: List[Card] = field(default_factory=list)
    graveyard: List[Card] = field(default_factory=list)
    exile: List[Card] = field(default_factory=list)
    battlefield: List[Permanent] = field(default_factory=list)
    mana_pool: Dict[str, int] = field(default_factory=dict)
    counters: Dict[str, int] = field(default_factory=dict)
    has_won: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert the player state to a dictionary for API calls."""
        return {
            "life": self.life,
            "hand": [card.name for card in self.hand],
            "library": [card.name for card in self.library],
            "graveyard": [card.name for card in self.graveyard],
            "exile": [card.name for card in self.exile],
            "mana_pool": self.mana_pool,
            "counters": self.counters,
            "battlefield": [perm.to_dict() for perm in self.battlefield],
            "has_won": self.has_won
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], player_name: str) -> 'PlayerState':
        """Create a PlayerState from a dictionary."""
        return cls(
            life=data.get('life', 20),
            hand=[Card.from_name(name) for name in data.get('hand', [])],
            library=[Card.from_name(name) for name in data.get('library', [])],
            graveyard=[Card.from_name(name) for name in data.get('graveyard', [])],
            exile=[Card.from_name(name) for name in data.get('exile', [])],
            battlefield=[Permanent.from_dict(perm_data, controller=player_name) for perm_data in data.get('battlefield', [])],
            mana_pool=data.get('mana_pool', {}),
            counters=data.get('counters', {}),
            has_won=data.get('has_won', False)
        )
        

@dataclass
class GameState:
    turn_counter: int = 1  # Which turn is it
    turn_player: str = "player1"  # Who's turn is it
    player_to_act: str = "player1"  # Who has the next decision to make
    phase: Phase = Phase.PRECOMBAT_MAIN
    player1_state: PlayerState = field(default_factory=PlayerState)
    player2_state: PlayerState = field(default_factory=PlayerState)
    stack: List[Dict[str, Any]] = field(default_factory=list)
    combat_attackers: List[str] = field(default_factory=list)  # Permanent IDs
    combat_blockers: Dict[str, List[str]] = field(default_factory=dict)  # attacker_id -> [blocker_ids]
    
    def has_p1_lost(self) -> bool:
        """Check if player 1 has lost the game."""
        return (self.player1_state.life <= 0 or 
                ('poison' in self.player1_state.counters.keys() and self.player1_state.counters['poison'] >= 10)
                or self.player2_state.has_won)
    
    def has_p2_lost(self) -> bool:
        """Check if player 2 has lost the game."""
        return (self.player2_state.life <= 0 or 
                ('poison' in self.player2_state.counters.keys() and self.player2_state.counters['poison'] >= 10)
                or self.player1_state.has_won)
    
    def is_game_over(self) -> bool:
        """Check if the game has ended."""
        return self.has_p1_lost() or self.has_p2_lost()
    
    def get_winner(self) -> Optional[str]:
        """Determine the winner if the game is over."""
        if not self.is_game_over():
            return None
        
        p1_lost = self.has_p1_lost()
        p2_lost = self.has_p2_lost()
        
        if not p1_lost and p2_lost:
            return "player1"
        elif not p2_lost and p1_lost:
            return "player2"
        else:
            return "draw"  # Both lose simultaneously
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert game state to a dictionary for API calls."""
        return {
            "turn_counter": self.turn_counter,
            "turn_player": self.turn_player,
            "player_to_act": self.player_to_act,
            "phase": self.phase.value,
            "player1": self.player1_state.to_dict(),
            "player2": self.player2_state.to_dict(),
            "stack": self.stack,
            "combat_attackers": self.combat_attackers,
            "combat_blockers": self.combat_blockers
        }
    
    def is_similar(self, other: 'GameState') -> bool:
        """Check if two game states are equal (excluding life totals and turn counter)."""
        # Compare basic turn information
        if (self.turn_player != other.turn_player or
            self.player_to_act != other.player_to_act or
            self.phase != other.phase):
            return False
        
        # Compare player states
        if not self._compare_player_state(self.player1_state, other.player1_state):
            return False
        if not self._compare_player_state(self.player2_state, other.player2_state):
            return False
        
        # Compare stack and combat
        if (self.stack != other.stack or
            self.combat_attackers != other.combat_attackers or
            self.combat_blockers != other.combat_blockers):
            return False
        
        return True

    def is_identical(self, other: 'GameState') -> bool:
        """Check if two game states are identical (excluding turn counter)."""
        return self.is_similar(other) and self.player1_state.life == other.player1_state.life and self.player2_state.life == other.player2_state.life

    def __eq__(self, other) -> bool:
        """Check if two game states are equal (for duplicate detection)."""
        if not isinstance(other, GameState):
            return False
        if not self.is_identical(other):
            return False
        return self.turn_counter == other.turn_counter
    
    def _compare_player_state(self, state1: 'PlayerState', state2: 'PlayerState') -> bool:
        """Compare two player states for equality (excluding life totals)."""

        # Compare simple fields
        simple_fieds = ['mana_pool', 'counters']
        for field in simple_fieds:
            if getattr(state1, field) != getattr(state2, field):
                return False

        # Compare cards in all zones except battlefield
        zones = ['hand', 'library', 'graveyard', 'exile']
        for zone in zones:
            names1 = sorted(card.name for card in getattr(state1, zone))
            names2 = sorted(card.name for card in getattr(state2, zone))
            if names1 != names2:
                return False

        # Compare battlefields
        bf1_representations = sorted([p.to_dict() for p in state1.battlefield], key=lambda x: x["name"])
        bf2_representations = sorted([p.to_dict() for p in state2.battlefield], key=lambda x: x["name"])
        
        return bf1_representations == bf2_representations
    
    def __hash__(self) -> int:
        """Generate hash for game state (for use in sets/dictionaries)."""
        # Use the dictionary representation for hashing
        import json
        state_dict = self.to_dict()
        # Convert to sorted JSON string for consistent hashing
        return hash(json.dumps(state_dict, sort_keys=True))
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GameState':
        """Create GameState from dictionary."""
        game_state = cls()
        game_state.turn_counter = data.get("turn_counter", 1)
        game_state.turn_player = data.get("turn_player", "player1")
        game_state.player_to_act = data.get("player_to_act", "player1")
        phase_str = data.get("phase", "precombat_main")
        game_state.phase = Phase(phase_str) if phase_str in Phase.__members__ else Phase.PRECOMBAT_MAIN
        game_state.player1_state = PlayerState.from_dict(data.get("player1", {}), "p1")
        game_state.player2_state = PlayerState.from_dict(data.get("player2", {}), "p2")
        game_state.stack = data.get("stack", [])
        game_state.combat_attackers = data.get("combat_attackers", [])
        game_state.combat_blockers = data.get("combat_blockers", {})
        return game_state


def create_initial_game_state(player1_cards: List[Card], player2_cards: List[Card]) -> GameState:
    """Create the initial game state for a 3-card blind matchup."""
    game_state = GameState()
    game_state.player1_state.hand = player1_cards.copy()
    game_state.player2_state.hand = player2_cards.copy()

    # Leyline check
    for card in player2_cards:
        if "If this card is in your opening hand, you may begin the game with it on the battlefield." in card.oracle_text:
            game_state.phase = Phase.PREGAME_P2
            break
    
    for card in player1_cards:
        if "If this card is in your opening hand, you may begin the game with it on the battlefield." in card.oracle_text:
            game_state.phase = Phase.PREGAME_P1
            break

    return game_state

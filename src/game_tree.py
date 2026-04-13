"""Game tree module for building and managing game state trees for 3-card blind Magic: The Gathering matchups."""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from uuid import uuid4
from dataclasses import dataclass, field
from .card_data import Card
from .game_state import GameState, create_initial_game_state
from .gemini_client import GeminiClient
import uuid
import json
import os


@dataclass
class GameTreeNode:
    """Represents a node in the game tree."""
    game_state: GameState
    parent: Optional['GameTreeNode'] = None
    children: List['GameTreeNode'] = field(default_factory=list)
    decision: Optional[str] = None  # Description of the decision that led to this node
    explanation: Optional[str] = None  # Detailed explanation from Gemini
    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    depth: int = 0
    is_terminal: bool = False
    outcome: Optional[str] = None  # "player1", "player2", or "draw"
    score: Optional[float] = None  # For min-max algorithm
    viability: Optional[float] = None  # Viability score from Gemini (1-10)
    is_transposition: bool = False  # True if this node is a transposition of another node
    transposition_target_id: Optional[str] = None  # ID of the node this is a transposition of
    is_loop: bool = False  # True if this node creates a loop with its parentage
    loop_type: Optional[str] = None  # "exact" or "near" to describe the type of loop
    loop_target_id: Optional[str] = None  # ID of the node this creates a loop with
    loop_hp_totals: Optional[List[tuple[int, int]]] = None  # List of (p1_hp, p2_hp) tuples for loop nodes
    alpha_beta_skip: bool = False  # Node is pruned by alpha-beta pruning
    
    def __post_init__(self):
        if self.game_state.is_game_over():
            self.is_terminal = True
            self.outcome = self.game_state.get_winner()
    
    def add_child(self, child_node: 'GameTreeNode') -> None:
        """Add a child node to this node."""
        child_node.parent = self
        child_node.depth = self.depth + 1
        self.children.append(child_node)

    def mark_alpha_beta_skip(self) -> None:
        """Mark this node and its children as skipped by alpha-beta pruning."""
        self.alpha_beta_skip = True
        for child in self.children:
            child.mark_alpha_beta_skip()
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert node to dictionary for serialization."""
        return {
            "node_id": self.node_id,
            "decision": self.decision,
            "explanation": self.explanation,
            "depth": self.depth,
            "is_terminal": self.is_terminal,
            "outcome": self.outcome,
            "score": self.score,
            "viability": self.viability,
            "is_transposition": self.is_transposition,
            "transposition_target_id": self.transposition_target_id,
            "is_loop": self.is_loop,
            "loop_type": self.loop_type,
            "loop_target_id": self.loop_target_id,
            "loop_hp_totals": self.loop_hp_totals,
            "alpha_beta_skip": self.alpha_beta_skip,
            "game_state": self.game_state.to_dict(),
            "children_ids": [child.node_id for child in self.children],
            "parent_id": self.parent.node_id if self.parent else None
        }


class GameTree:
    """Represents the complete game tree for a matchup."""
    
    def __init__(self, player1_cards: List[Card], player2_cards: List[Card]):
        self.player1_cards = player1_cards
        self.player2_cards = player2_cards
        
        # Create initial game state
        initial_state = create_initial_game_state(player1_cards, player2_cards)

        # Create root node
        self.root = GameTreeNode(game_state=initial_state)

        self.nodes: Dict[str, GameTreeNode] = {self.root.node_id: self.root}
        self.terminal_nodes: List[GameTreeNode] = []
        self.max_depth = 0
        self.total_nodes = 1
        self.optimal_path: Optional[List[GameTreeNode]] = None
    
    def add_node(self, parent_node: GameTreeNode, new_game_state: GameState, decision: str, 
               viability: float, explanation: str) -> GameTreeNode:
        """Add a new node to game tree."""
        new_node = GameTreeNode(
            game_state=new_game_state,
            decision=decision,
            viability=viability,
            explanation=explanation
        )
        
        parent_node.add_child(new_node)
        self.nodes[new_node.node_id] = new_node
        self.total_nodes += 1
        
        if new_node.depth > self.max_depth:
            self.max_depth = new_node.depth

        # Check if the new node is a terminal node (via game over)
        if new_node.is_terminal:
            self.terminal_nodes.append(new_node)
            return new_node
        
        # Check if the new node forms an exact loop
        exact_loop_node = self._check_for_exact_loop(new_node)
        if exact_loop_node:
            new_node.is_loop = True
            new_node.loop_type = "exact"
            new_node.loop_target_id = exact_loop_node.node_id
            new_node.is_terminal = True
            self.terminal_nodes.append(new_node)
            return new_node
        
        # Check if the new node forms a near loop
        near_loop_node = self._check_for_near_loop(new_node)
        if near_loop_node:
            new_node.is_loop = True
            new_node.loop_type = "near"
            new_node.loop_target_id = near_loop_node.node_id
            new_node.is_terminal = True
            self.terminal_nodes.append(new_node)
            return new_node
        
        # Check if the new node forms a transposition
        transposition_node = self._check_for_transposition(new_node)
        if transposition_node:
            new_node.is_transposition = True
            new_node.transposition_target_id = transposition_node.node_id
            new_node.is_terminal = True
            self.terminal_nodes.append(new_node)
        
        return new_node
    
    def is_predecessor(self, potential_predecessor: GameTreeNode, node: GameTreeNode) -> bool:
        """Check if potential_predecessor is a predecessor of node."""
        current = node.parent
        while current:
            if current.node_id == potential_predecessor.node_id:
                return True
            current = current.parent
        return False
    
    def _check_for_exact_loop(self, new_node: GameTreeNode) -> Optional[GameTreeNode]:
        """Check if new_node creates an exact loop with any predecessor."""
        current = new_node.parent
        while current:
            if current.game_state.is_identical(new_node.game_state) and new_node.game_state.turn_counter > current.game_state.turn_counter:
                return current
            current = current.parent
        return None
    
    def _check_for_near_loop(self, new_node: GameTreeNode) -> Optional[GameTreeNode]:
        """Check if new_node creates a near loop (same state but different life totals)."""
        current = new_node.parent
        while current:
            if current.game_state.is_similar(new_node.game_state):
                return current
            current = current.parent
        return None
    
    def _check_for_transposition(self, new_node: GameTreeNode) -> Optional[GameTreeNode]:
        """Check if new_node creates a transposition with any existing node."""
        for _, existing_node in self.nodes.items():
            if (existing_node.node_id != new_node.node_id and 
                not existing_node.is_loop and
                not existing_node.is_transposition and
                existing_node.game_state.is_identical(new_node.game_state) and
                not self.is_predecessor(existing_node, new_node)):
                return existing_node
        return None

    def expand_node(self, node: GameTreeNode, gemini_client: GeminiClient, max_children: int = 10) -> List[GameTreeNode]:
        """Expand a node by generating decisions using the Gemini client and creating child nodes.
        
        Args:
            node: The node to expand
            gemini_client: The Gemini client to use for decision generation
            max_children: Maximum number of children to create (to limit branching factor)
            
        Returns:
            List of newly created child nodes
        """
        if node.is_terminal:
            return []
        
        if len(node.children) > 0:
            print(f"Warning: Node {node.node_id} already has {len(node.children)} children")
            return node.children
        
        # Generate decisions using Gemini
        decisions = gemini_client.generate_decisions(node.game_state, self.player1_cards, self.player2_cards)
        
        if not decisions:
            print(f"No decisions generated for node {node.node_id}")
            return []
        
        # Limit the number of children to prevent explosion
        decisions = decisions[:max_children]
        
        # Create child nodes for each decision
        child_nodes = []
        seen_states = set()  # Track game states we've already seen
        
        for decision in decisions:
            print(f"------> Option: {decision['decision']}")

            # Parse the resulting game state from the decision
            resulting_state_dict = decision.get("resulting_game_state", {})
            
            # Create a new GameState from the dictionary
            new_game_state = GameState.from_dict(resulting_state_dict)
            
            # Validate that player_to_act has properly swapped to the other player
            current_player_to_act = node.game_state.player_to_act
            new_player_to_act = new_game_state.player_to_act
            
            if current_player_to_act == new_player_to_act:
                print(f"Invalid game state: player_to_act did not swap from {current_player_to_act} to other player")
                print(f"Skipping decision: {decision['decision']}")
                continue
                                
            # Check if this game state is a duplicate
            state_hash = hash(new_game_state)
            if state_hash in seen_states:
                print(f"Skipping duplicate game state for decision: {decision['decision']}")
                continue
            seen_states.add(state_hash)
            
            # Create child node
            child_node = self.add_node(
                parent_node=node,
                new_game_state=new_game_state,
                decision=decision.get("decision", "Unknown action"),
                viability=decision.get("viability"),
                explanation=decision.get("explanation")
            )
            
            child_nodes.append(child_node)
        
        print(f"Expanded node {node.node_id}: created {len(child_nodes)} children from {len(decisions)} decisions")
        return child_nodes
    
    def expand_nodes_batch(self, nodes: List[GameTreeNode], gemini_client: GeminiClient, max_children: int = 10) -> Dict[str, List[GameTreeNode]]:
        """Expand multiple nodes in parallel using batch processing.
        
        Args:
            nodes: List of nodes to expand
            gemini_client: The Gemini client to use for decision generation
            max_children: Maximum number of children to create per node
            
        Returns:
            Dictionary mapping node IDs to lists of newly created child nodes
        """
        if not nodes:
            return {}
        
        # Filter out nodes that shouldn't be expanded
        valid_nodes: List[GameTreeNode] = []
        for node in nodes:
            if node.is_terminal:
                print(f"Skipping terminal node {node.node_id}")
                continue
            if len(node.children) > 0:
                print(f"Warning: Node {node.node_id} already has {len(node.children)} children")
                continue
            if node.alpha_beta_skip:
                print(f"Skipping node {node.node_id} due to alpha-beta pruning")
                continue
            valid_nodes.append(node)
        
        if not valid_nodes:
            print("No valid nodes to expand")
            return {}
        
        # Prepare batch input for Gemini
        batch_input = []
        for node in valid_nodes:
            batch_input.append((node.game_state, self.player1_cards, self.player2_cards))
        
        # Generate decisions in batch
        try:
            batch_decisions = gemini_client.generate_decisions_batch(batch_input)
        except Exception as e:
            print(f"Error in batch expansion: {e}")
            print("Falling back to sequential expansion...")
            # Fallback to sequential processing
            return self._expand_nodes_sequential(valid_nodes, gemini_client, max_children)
        
        # Process results and create child nodes
        results = {}
        for i, (node, decisions) in enumerate(zip(valid_nodes, batch_decisions)):
            if not decisions:
                print(f"No decisions generated for node {node.node_id}")
                results[node.node_id] = []
                continue
            
            # Limit the number of children
            decisions = decisions[:max_children]
            
            # Create child nodes for each decision
            child_nodes = []
            seen_states = set()
            
            for decision in decisions:
                print(f"------> Option: {decision['decision']}")

                # Parse the resulting game state from the decision
                resulting_state_dict = decision.get("resulting_game_state", {})
                
                # Create a new GameState from the dictionary
                new_game_state = GameState.from_dict(resulting_state_dict)
                
                # Validate that player_to_act has properly swapped to the other player
                current_player_to_act = node.game_state.player_to_act
                new_player_to_act = new_game_state.player_to_act
                
                if current_player_to_act == new_player_to_act:
                    print(f"Invalid game state for node {node.node_id}: player_to_act did not swap")
                    print(f"Skipping decision: {decision['decision']}")
                    continue
                    
                # Check if this game state is a duplicate
                state_hash = hash(new_game_state)
                if state_hash in seen_states:
                    print(f"Skipping duplicate game state for node {node.node_id}")
                    continue
                seen_states.add(state_hash)
                
                # Create child node
                child_node = self.add_node(
                    parent_node=node,
                    new_game_state=new_game_state,
                    decision=decision.get("decision", "Unknown action"),
                    viability=decision.get("viability"),
                    explanation=decision.get("explanation")
                )
                
                child_nodes.append(child_node)
            
            print(f"Expanded node {node.node_id}: created {len(child_nodes)} children from {len(decisions)} decisions")
            results[node.node_id] = child_nodes
        
        return results
    
    def _expand_nodes_sequential(self, nodes: List[GameTreeNode], gemini_client: GeminiClient, max_children: int = 10) -> Dict[str, List[GameTreeNode]]:
        """Fallback method for sequential node expansion."""
        results = {}
        for node in nodes:
            results[node.node_id] = self.expand_node(node, gemini_client, max_children)
        return results
            
    def save_to_file(self, filepath: str) -> None:
        """Save the game tree to a JSON file."""
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # Prepare data for serialization
        tree_data = {
            "metadata": {
                "player1_cards": [card.name for card in self.player1_cards],
                "player2_cards": [card.name for card in self.player2_cards],
                "total_nodes": self.total_nodes,
                "max_depth": self.max_depth,
                "optimal_path": [node.node_id for node in self.optimal_path] if self.optimal_path else None
            },
            "nodes": {}
        }
        
        # Serialize all nodes
        for node_id, node in self.nodes.items():
            tree_data["nodes"][node_id] = node.to_dict()
        
        # Save to file
        with open(filepath, 'w') as f:
            json.dump(tree_data, f, indent=2)
        
        print(f"Game tree saved to {filepath} with {self.total_nodes} nodes")
    
    @classmethod
    def load_from_file(cls, filepath: str) -> 'GameTree':
        """Load a game tree from a JSON file."""
        with open(filepath, 'r') as f:
            tree_data = json.load(f)
        
        # Extract metadata
        metadata = tree_data["metadata"]
        player1_cards = [Card.from_name(name) for name in metadata["player1_cards"]]
        player2_cards = [Card.from_name(name) for name in metadata["player2_cards"]]
        
        # Create tree instance
        tree = cls(player1_cards, player2_cards)
        tree.total_nodes = metadata["total_nodes"]
        tree.max_depth = metadata["max_depth"]
        tree.optimal_path = None  # Will be set after nodes are loaded
        
        # Clear the default nodes and load from file
        tree.nodes = {}
        tree.terminal_nodes = []
        
        # First pass: create all nodes
        for node_id, node_data in tree_data["nodes"].items():
            # Create game state from dictionary
            game_state = GameState.from_dict(node_data["game_state"])
            
            # Create node
            node = GameTreeNode(
                game_state=game_state,
                decision=node_data["decision"],
                explanation=node_data["explanation"],
                node_id=node_data["node_id"],
                depth=node_data["depth"],
                is_terminal=node_data["is_terminal"],
                outcome=node_data["outcome"],
                score=node_data["score"],
                viability=node_data["viability"],
                is_transposition=node_data.get("is_transposition", False),
                transposition_target_id=node_data.get("transposition_target_id"),
                is_loop=node_data.get("is_loop", False),
                loop_target_id=node_data.get("loop_target_id"),
                loop_hp_totals=node_data.get("loop_hp_totals"),
                loop_type=node_data.get("loop_type"),
                alpha_beta_skip=node_data.get("alpha_beta_skip")
            )
            
            tree.nodes[node_id] = node
        
        # Second pass: establish relationships
        for node_id, node_data in tree_data["nodes"].items():
            node = tree.nodes[node_id]
            
            # Set parent
            if node_data["parent_id"]:
                node.parent = tree.nodes[node_data["parent_id"]]
            
            # Set children
            for child_id in node_data["children_ids"]:
                child = tree.nodes[child_id]
                node.children.append(child)
        
        # Set root node (find node with no parent)
        root_node = None
        for node in tree.nodes.values():
            if node.parent is None:
                root_node = node
                break
        
        tree.root = root_node or next(iter(tree.nodes.values())) if tree.nodes else None
        
        # Collect terminal nodes
        tree.terminal_nodes = [node for node in tree.nodes.values() if node.is_terminal]
        
        # Restore optimal path if it exists
        optimal_path_ids = metadata.get("optimal_path")
        if optimal_path_ids:
            tree.optimal_path = []
            for node_id in optimal_path_ids:
                if node_id in tree.nodes:
                    tree.optimal_path.append(tree.nodes[node_id])
        
        print(f"Game tree loaded from {filepath} with {tree.total_nodes} nodes")
        return tree


def create_game_trees(player1_cards: List[Card], player2_cards: List[Card]) -> Dict[str, GameTree]:
    """Create two game trees, one for each starting player."""
    trees = {}
    
    # Tree where player1 starts
    trees["player1_starts"] = GameTree(player1_cards, player2_cards)
    
    # Tree where player2 starts
    trees["player2_starts"] = GameTree(player2_cards, player1_cards)
    
    return trees

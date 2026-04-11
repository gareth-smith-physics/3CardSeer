"""Utility module for managing saved game trees."""

import os
from typing import Dict, List, Optional
from .game_tree import GameTree


class TreeManager:
    """Manages saving and loading of game trees."""
    
    def __init__(self, save_directory: str = "saved_trees"):
        self.save_directory = save_directory
        os.makedirs(save_directory, exist_ok=True)
    
    def save_tree(self, tree: GameTree, matchup_name: str) -> str:
        """Save a game tree with a descriptive name."""
        filename = f"{matchup_name.replace(' ', '_')}.json"
        filepath = os.path.join(self.save_directory, filename)
        tree.save_to_file(filepath)
        return filepath
    
    def load_tree(self, matchup_name: str) -> Optional[GameTree]:
        """Load a game tree by name."""
        filename = f"{matchup_name.replace(' ', '_')}.json"
        filepath = os.path.join(self.save_directory, filename)
        
        if not os.path.exists(filepath):
            return None
        
        return GameTree.load_from_file(filepath)
    
    def list_saved_trees(self) -> List[str]:
        """List all saved game trees."""
        if not os.path.exists(self.save_directory):
            return []
        
        files = [f for f in os.listdir(self.save_directory) if f.endswith('.json')]
        return [f.replace('.json', '').replace('_', ' ') for f in files]
    
    def delete_tree(self, matchup_name: str) -> bool:
        """Delete a saved game tree."""
        filename = f"{matchup_name.replace(' ', '_')}.json"
        filepath = os.path.join(self.save_directory, filename)
        
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False
    
    def get_tree_info(self, matchup_name: str) -> Optional[Dict]:
        """Get metadata about a saved tree without loading it fully."""
        import json
        
        filename = f"{matchup_name.replace(' ', '_')}.json"
        filepath = os.path.join(self.save_directory, filename)
        
        if not os.path.exists(filepath):
            return None
        
        try:
            with open(filepath, 'r') as f:
                tree_data = json.load(f)
            
            metadata = tree_data.get("metadata", {})
            return {
                "player1_cards": metadata.get("player1_cards", []),
                "player2_cards": metadata.get("player2_cards", []),
                "starting_player": metadata.get("starting_player", "unknown"),
                "total_nodes": metadata.get("total_nodes", 0),
                "max_depth": metadata.get("max_depth", 0),
                "file_size": os.path.getsize(filepath)
            }
        except Exception as e:
            print(f"Error reading tree info: {e}")
            return None

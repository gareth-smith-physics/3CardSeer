#!/usr/bin/env python3
"""
Visualize a saved game tree using the visual display system.
Usage: python visualize_tree.py <tree_name>
"""

import argparse
from src.gemini_client import create_gemini_client
from src.tree_manager import TreeManager
from src.visual_display import VisualDisplayApp


def main():
    """Main function to visualize a saved tree."""
    parser = argparse.ArgumentParser(description="Visualize a saved game tree")
    parser.add_argument("tree_name", help="Name of the saved tree to load")
    parser.add_argument("--list", action="store_true", help="List all available saved trees")
    
    args = parser.parse_args()
    
    # Create tree manager
    tree_manager = TreeManager()
    
    # List trees if requested
    if args.list:
        trees = tree_manager.list_saved_trees()
        if trees:
            print("Available saved trees:")
            for i, tree in enumerate(trees, 1):
                info = tree_manager.get_tree_info(tree)
                if info:
                    print(f"  {i}. {tree}")
                    print(f"     P1: {', '.join(info['player1_cards'])}")
                    print(f"     P2: {', '.join(info['player2_cards'])}")
                    print(f"     Nodes: {info['total_nodes']}, Depth: {info['max_depth']}")
                    print()
                else:
                    print(f"  {i}. {tree}")
        else:
            print("No saved trees found.")
        return
    
    tree_name = args.tree_name
    
    print(f"🎨 Visualizing Tree: {tree_name}")
    print("=" * 40)
    
    try:
        # Load the tree
        print(f"📂 Loading tree '{tree_name}'...")
        game_tree = tree_manager.load_tree(tree_name)
        
        if not game_tree:
            print(f"❌ Tree '{tree_name}' not found.")
            print("Use --list to see available trees.")
            return
        
        print(f"✅ Loaded tree with {game_tree.total_nodes} nodes")
        print(f"   Max depth: {game_tree.max_depth}")
        print(f"   Root node ID: {game_tree.root.node_id}")
        
        # Test initial game state
        print("🎯 Setting up game state...")
        game_state = game_tree.root.game_state
        game_state.turn_player = "player1"
        game_state.player_to_act = "player1"
        
        print(f"Turn: {game_state.turn_counter}, Player: {game_state.turn_player}")
        print(f"Player to act: {game_state.player_to_act}")
        print(f"P1 hand: {[c.name for c in game_state.player1_state.hand]}")
        print(f"P2 hand: {[c.name for c in game_state.player2_state.hand]}")
        
        # Test Gemini client
        print("\n🤖 Setting up Gemini integration...")
        client = create_gemini_client()
        print(f"Model: {client.model_name}")
        
        print(f"Total nodes: {game_tree.total_nodes}")
        
        # Launch visual display
        print("\n🖥️  Launching visual display...")
        print("   - Use the main window to open tree and state displays")
        print("   - Click on nodes to view game states")
        print("   - Click orange + buttons to expand nodes")
        print("   - Tree will be saved when you close the window")
        
        # Create and run visual app
        app = VisualDisplayApp(game_tree, client)
        
        print("\n🎉 Visual display running!")
        print("   Close the GUI window to save and exit.")
        
        # Run the GUI
        app.run()
        
        # Save the tree when the display is closed
        print(f"\n💾 Saving tree as '{tree_name}'...")
        save_path = tree_manager.save_tree(game_tree, tree_name)
        print(f"✅ Tree saved to: {save_path}")
        print(f"   Saved {game_tree.total_nodes} nodes with max depth {game_tree.max_depth}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

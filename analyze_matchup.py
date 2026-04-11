#!/usr/bin/env python3
"""
Automatic game tree population and analysis script for 3-card blind matchups.
Usage: python analyze_matchup.py <card1> <card2> <card3> <card4> <card5> <card6> [options]
"""

import argparse
import sys
from src.matchup_analyzer import AutoTreeAnalyzer, AnalysisConfig
from src.card_data import Card


def main():
    """Main function for the auto tree analyzer."""
    parser = argparse.ArgumentParser(
        description="Automatically analyze 3-card blind matchups",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python analyze_matchup.py 'Mana Vault' 'Ancient Tomb' 'Lodestone Golem' 'Mutavault' 'Mox Jet' 'Aunties Sentence' --matchup-name 'Lodestone vs Aunties'
  
To see available analysis settings:
  python analyze_matchup.py --help
        """
    )

    defaults = AnalysisConfig()

    parser.add_argument("cards", nargs='*', help="6 card names (3 for each player), optional when using --load-tree")
    parser.add_argument("--threshold", type=float, default=defaults.viability_threshold,
                       help="Viability threshold for expansion")
    parser.add_argument("--max-depth", type=int, default=defaults.max_depth,
                       help="Maximum tree depth")
    parser.add_argument("--max-nodes", type=int, default=defaults.max_nodes,
                       help="Maximum total nodes")
    parser.add_argument("--max-branches", type=int, default=defaults.max_branches_per_node,
                       help="Maximum branches per node")
    parser.add_argument("--timeout", type=int, default=defaults.analysis_timeout,
                       help="Analysis timeout in seconds")
    parser.add_argument("--n-threads", type=int, default=defaults.n_threads,
                       help="Number of threads for parallel node expansion")
    parser.add_argument("--verbose", action="store_true",
                       help="Enable verbose output")
    parser.add_argument("--matchup-name", required=True,
                       help="Name for the matchup")
    parser.add_argument("--load-tree", action="store_true",
                       help="Load tree from file instead of creating new one")
    parser.add_argument("--skip-population", action="store_true",
                       help="Skip tree population and analyze existing tree only")
    
    args = parser.parse_args()
    
    # Validate arguments
    if len(args.cards) != 6 and not args.load_tree:
        print("Error: Exactly 6 card names required (3 for each player) when not loading tree")
        return 1
    
    if args.skip_population and not args.load_tree:
        print("Error: --skip-population requires --load-tree to be specified")
        return 1
    
    # Create configuration
    config = AnalysisConfig(
        viability_threshold=args.threshold,
        max_depth=args.max_depth,
        max_nodes=args.max_nodes,
        max_branches_per_node=args.max_branches,
        analysis_timeout=args.timeout,
        n_threads=args.n_threads
    )
    
    # Create cards using Scryfall API (only if not loading tree)
    p1_cards = None
    p2_cards = None
    try:
        p1_cards = [Card.from_name(name) for name in args.cards[:3]]
        p2_cards = [Card.from_name(name) for name in args.cards[3:]]
    except Exception as e:
        print(f"Error fetching card data: {e}")
        print("   Please check card names and try again.")
        return 1
    
    # Run analysis
    analyzer = AutoTreeAnalyzer(config)
    analyzer.matchup_name = args.matchup_name
    
    result = analyzer.analyze_matchup(p1_cards, p2_cards, args.load_tree, args.skip_population)
    if result is None:
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

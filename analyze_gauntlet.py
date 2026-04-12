#!/usr/bin/env python3
"""
Gauntlet analyzer script for computing matchup results between decks.
Usage: python analyze_gauntlet.py <gauntlet_csv_file> [options]
"""

import argparse
import csv
import hashlib
import sys
import time
from typing import List, Dict, Tuple
from src.matchup_analyzer import AutoTreeAnalyzer, AnalysisConfig, AnalysisResult
from src.card_data import Card


def get_deck_hash(cards: List[str]) -> str:
    """Generate a unique hash for a deck based on card names."""
    # Sort cards to ensure consistent hashing regardless of order
    sorted_cards = sorted(cards)
    deck_string = "|".join(sorted_cards)
    return hashlib.md5(deck_string.encode()).hexdigest()[:8]


def parse_gauntlet_csv(file_path: str) -> List[List[str]]:
    """Parse gauntlet CSV file and return list of decks (each deck is list of 3 card names)."""
    decks = []
    try:
        with open(file_path, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                if len(row) == 3:
                    # Clean up card names (remove quotes if present)
                    deck = [card.strip().strip("'\"") for card in row]
                    decks.append(deck)
                else:
                    print(f"Warning: Skipping row with {len(row)} cards (expected 3): {row}")
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        sys.exit(1)
    
    return decks


def compute_matchup_grid(decks: List[List[str]], config: AnalysisConfig) -> Dict[Tuple[int, int], float]:
    """Compute matchup results for all pairs of decks."""
    n_decks = len(decks)
    matchup_grid = {}
    
    print(f"Computing matchups for {n_decks} decks...")
    print(f"Total matchups to analyze: {n_decks * (n_decks - 1) // 2}")
    
    matchup_count = 0
    for i in range(n_decks):
        for j in range(i + 1, n_decks):
            matchup_count += 1
            print(f"\nAnalyzing matchup {matchup_count}/{n_decks * (n_decks - 1) // 2}")
            print(f"Deck {i+1}: {decks[i]} vs Deck {j+1}: {decks[j]}")
            
            try:
                # Create Card objects
                p1_cards = [Card.from_name(name) for name in decks[i]]
                p2_cards = [Card.from_name(name) for name in decks[j]]
                
                # Run analysis
                analyzer = AutoTreeAnalyzer(config)
                deck1_hash = get_deck_hash(decks[i])
                deck2_hash = get_deck_hash(decks[j])
                analyzer.matchup_name = f"{deck1_hash}_vs_{deck2_hash}"
                
                start_time = time.time()
                result = analyzer.analyze_matchup(p1_cards, p2_cards, load_tree=True, skip_population=False)
                analysis_time = time.time() - start_time
                
                if result is not None:
                    # Store result (4 = WW, 0 = LL)
                    matchup_grid[(i, j)] = 2 * result.outcome_float
                    matchup_grid[(j, i)] = 4 - 2 *result.outcome_float  # Symmetric matchup
                    
                    if config.verbose:
                        print(f"  Result: {result.outcome_string} ({result.outcome_float:.3f})")
                        print(f"  Analysis time: {analysis_time:.2f}s")
                        print(f"  Tree nodes: {result.total_nodes}, Max depth: {result.max_depth}")
                else:
                    print(f"  Error: Analysis failed for this matchup")
                    matchup_grid[(i, j)] = 0.0
                    matchup_grid[(j, i)] = 0.0
                    
            except Exception as e:
                print(f"  Error analyzing matchup: {e}")
                matchup_grid[(i, j)] = 0.0
                matchup_grid[(j, i)] = 0.0
    
    return matchup_grid


def save_matchup_results(decks: List[List[str]], matchup_grid: Dict[Tuple[int, int], float], output_file: str):
    """Save matchup results to CSV file."""
    n_decks = len(decks)
    
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write header rows with deck names
            header_rows = [['','','Card 1'], ['','','Card 2'], ['Card 1','Card 2','Card 3']]
            for deck in decks:
                for i in range(3):
                    header_rows[i].append(deck[i])
            for i in range(3):
                writer.writerow(header_rows[i])
            
            # Write matchup grid
            for i in range(n_decks):
                row = list(decks[i])
                for j in range(n_decks):
                    if i == j:
                        row.append('X')  # Same deck matchup
                    else:
                        value = matchup_grid.get((i, j), 0.0)
                        row.append(f'{value:.3f}')
                writer.writerow(row)
        
        print(f"\nMatchup results saved to '{output_file}'")
        
    except Exception as e:
        print(f"Error saving results: {e}")
        sys.exit(1)


def print_summary(decks: List[List[str]], matchup_grid: Dict[Tuple[int, int], float]):
    """Print summary of matchup results."""
    n_decks = len(decks)
    
    print(f"\n{'='*60}")
    print("GAUNTLET SUMMARY")
    print(f"{'='*60}")

    # Print matrix in CSV format with proper alignment
    print("\nMatchup Matrix:")
    
    # Calculate column widths for proper alignment
    card_widths = [max(len(deck[i]) for deck in decks) for i in range(3)]  # Width for card name columns
    deck_widths = [max([len(card) for card in deck]) for deck in decks]    # Width for body columns
    
    # Print header rows with deck names (matching CSV format)
    header_rows = [f"{'':>{card_widths[0]}}  {'':>{card_widths[1]}}  {'Card 1':>{card_widths[2]}} | ",
                   f"{'':>{card_widths[0]}}  {'':>{card_widths[1]}}  {'Card 2':>{card_widths[2]}} | ",
                   f"{'Card 1':>{card_widths[0]}}  {'Card 2':>{card_widths[1]}}  {'Card 3':>{card_widths[2]}} | "]
    for j in range(len(decks)):
        for i in range(3):
            header_rows[i] += f"{decks[j][i]:{deck_widths[j]}} | "
    for row in header_rows:
        print(row)
    
    # Print separator line
    separator = "-" * (card_widths[0] + card_widths[1] + card_widths[2] + 4 + sum(deck_widths) + 3 * (len(decks) - 1) + 5)
    print(separator)
    
    # Print matchup grid
    for i in range(n_decks):
        # Print deck cards
        row_str = f"{decks[i][0]:>{card_widths[0]}}, {decks[i][1]:>{card_widths[1]}}, {decks[i][2]:>{card_widths[2]}} | "
        
        # Print matchup values
        for j in range(n_decks):
            if i == j:
                row_str += f"{'X':>{deck_widths[j]}} | "
            else:
                value = matchup_grid.get((i, j), 0.0)
                row_str += f"{value:{deck_widths[j]}.3f} | "
        
        print(row_str)
    
        
    print(f"\nTotal decks analyzed: {n_decks}")
    print(f"Total matchups analyzed: {n_decks * (n_decks - 1) // 2}")


def main():
    """Main function for gauntlet analyzer."""
    parser = argparse.ArgumentParser(
        description="Analyze matchups between decks in a gauntlet format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python analyze_gauntlet.py example_gauntlet.csv --output matchup_results.csv
  
The gauntlet CSV should have 3 card names per row, representing one deck.
        """
    )
    
    defaults = AnalysisConfig()
    
    parser.add_argument("gauntlet_file", help="CSV file containing deck lists (3 cards per row)")
    parser.add_argument("--output", default="matchup_results.csv", help="Output CSV file for results")
    parser.add_argument("--threshold", type=float, default=defaults.viability_threshold,
                       help="Viability threshold for tree expansion")
    parser.add_argument("--max-depth", type=int, default=defaults.max_depth,
                       help="Maximum tree depth")
    parser.add_argument("--max-nodes", type=int, default=defaults.max_nodes,
                       help="Maximum total nodes")
    parser.add_argument("--max-branches", type=int, default=defaults.max_branches_per_node,
                       help="Maximum branches per node")
    parser.add_argument("--timeout", type=int, default=defaults.analysis_timeout,
                       help="Analysis timeout in seconds")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--dry-run", action="store_true", help="Dry run, don't make any API calls")
    
    args = parser.parse_args()
    
    # Parse gauntlet file
    print(f"Loading gauntlet from '{args.gauntlet_file}'...")
    decks = parse_gauntlet_csv(args.gauntlet_file)
    
    if len(decks) < 2:
        print("Error: At least 2 decks required for matchup analysis")
        return 1
    
    print(f"Found {len(decks)} decks:")
    for i, deck in enumerate(decks):
        print(f"  Deck {i+1}: {', '.join(deck)}")
    
    # Create configuration
    config = AnalysisConfig(
        viability_threshold=args.threshold,
        max_depth=args.max_depth,
        max_nodes=args.max_nodes,
        max_branches_per_node=args.max_branches,
        analysis_timeout=args.timeout,
        dry_run=args.dry_run,
        verbose=args.verbose
    )
    
    # Compute matchups
    start_time = time.time()
    matchup_grid = compute_matchup_grid(decks, config)
    total_time = time.time() - start_time
    
    # Save results
    save_matchup_results(decks, matchup_grid, args.output)
    
    # Print summary
    print_summary(decks, matchup_grid)
    
    print(f"\nTotal analysis time: {total_time:.2f} seconds")
    print(f"Average time per matchup: {total_time / (len(decks) * (len(decks) - 1) // 2):.2f} seconds")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

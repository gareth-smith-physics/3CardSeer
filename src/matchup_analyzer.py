"""
Automatic game tree population and analysis system for 3-card blind matchups.
"""

import time
from typing import List, Dict, Optional
from dataclasses import dataclass
from collections import deque

from .game_tree import GameTree, GameTreeNode
from .card_data import Card
from .gemini_client import create_gemini_client
from .tree_manager import TreeManager


@dataclass
class AnalysisConfig:
    """Configuration for tree analysis."""
    viability_threshold: float = 6.0  # Minimum viability to expand a node
    max_depth: int = 20  # Maximum tree depth to prevent infinite growth
    max_nodes: int = 500  # Maximum total nodes to prevent memory issues
    max_branches_per_node: int = 8  # Maximum branches to consider per node
    analysis_timeout: int = 3000  # Maximum analysis time in seconds
    n_threads: int = 16  # Number of threads for parallel node expansion


@dataclass
class AnalysisResult:
    """Results of tree analysis."""
    player1_cards: List[str]
    player2_cards: List[str]
    outcome_string: str
    outcome_float: float
    optimal_path_p1: List[GameTreeNode]
    optimal_path_p2: List[GameTreeNode]
    total_nodes: int
    max_depth: int
    analysis_time: float
    terminal_nodes_by_outcome: Dict[str, int]


class AutoTreeAnalyzer:
    """Automatic game tree population and analysis system."""
    
    def __init__(self, config: AnalysisConfig):
        self.config = config
        self.gemini_client = create_gemini_client(max_workers=config.n_threads)
        self.tree_manager = TreeManager()
        self.matchup_name = "auto_analysis"
        
    def analyze_matchup(self, p1_cards: List[Card], p2_cards: List[Card], load_tree: bool = False, skip_population: bool = False) -> AnalysisResult:
        """Analyze a 3-card blind matchup and determine optimal play."""
        start_time = time.time()

        print(f"Analyzing matchup:")
        print(f"   Player 1: {', '.join([c.name for c in p1_cards])}")
        print(f"   Player 2: {', '.join([c.name for c in p2_cards])}")
        print(f"   Viability threshold: {self.config.viability_threshold}")
        print(f"   Max depth: {self.config.max_depth}")
        print()

        # Create or load game trees for both starting players
        trees: Dict[str, GameTree] = {}
        for starting_player in ["player1", "player2"]:
            print()
            print("*"*60)
            if load_tree:
                print(f"Loading tree with {starting_player} starting...")
                tree = self._load_tree(f"{self.matchup_name}_{starting_player}")
                if tree is not None:
                    trees[starting_player] = tree
                    print(f"   Tree loaded: {tree.total_nodes} nodes, max depth {tree.max_depth}")
                else:
                    print(f"   Could not load tree for {starting_player}, falling back to building new tree")
                    load_tree = False  # Fall back to building new trees
            
            if starting_player not in trees:
                print(f"Initializing tree with {starting_player} starting...")
                tree = GameTree(p1_cards, p2_cards) if starting_player == "player1" else GameTree(p2_cards, p1_cards)
                trees[starting_player] = tree

            if not skip_population:
                self._populate_and_analyze_tree(tree, starting_player)
                print(f"   Tree populated and analyzed: {tree.total_nodes} nodes, max depth {tree.max_depth}")
            else:
                # If skipping population, still need to analyze the loaded tree
                self._analyze_current_tree_state(tree)

        # Final analysis to compute optimal paths
        print("\nComputing optimal paths...")
        p1_result = self._analyze_tree(trees["player1"])
        p2_result = self._analyze_tree(trees["player2"])

        # Save optimal paths to trees
        trees["player1"].optimal_path = p1_result["optimal_path"]
        trees["player2"].optimal_path = p2_result["optimal_path"]

        self.tree_manager.save_tree(trees["player1"], f"{self.matchup_name}_player1")
        self.tree_manager.save_tree(trees["player2"], f"{self.matchup_name}_player2")
        
        # Determine overall winner
        outcome_str, outcome_float = self._determine_overall_winner(p1_result, p2_result)
        
        # Choose the optimal path (prefer the starting player's perspective)
        optimal_path_p1 = p1_result["optimal_path"]
        optimal_path_p2 = p2_result["optimal_path"]
        
        analysis_time = time.time() - start_time
        
        # Calculate combined statistics
        total_nodes = trees["player1"].total_nodes + trees["player2"].total_nodes
        max_depth = max(trees["player1"].max_depth, trees["player2"].max_depth)
        
        # Count terminal nodes by outcome
        terminal_counts = {"player1": 0, "player2": 0, "draw": 0}
        for tree in trees.values():
            for node in tree.terminal_nodes:
                if node.outcome:
                    terminal_counts[node.outcome] += 1
        
        result = AnalysisResult(
            player1_cards=[card.name for card in p1_cards],
            player2_cards=[card.name for card in p2_cards],
            outcome_string=outcome_str,
            outcome_float=outcome_float,
            optimal_path_p1=optimal_path_p1,
            optimal_path_p2=optimal_path_p2,
            total_nodes=total_nodes,
            max_depth=max_depth,
            analysis_time=analysis_time,
            terminal_nodes_by_outcome=terminal_counts
        )
        
        self._print_results(result)
        return result
    
    def _populate_and_analyze_tree(self, tree: GameTree, starting_player: str):
        """Populate the game tree using batch expansion with integrated analysis."""

        # Clear and reanalyze the tree before expansion begins
        self._clear_tree_scores(tree)
        self._analyze_current_tree_state(tree)

        # Recover nodes to expand from previous run if available
        nodes_to_expand = deque()
        if len(tree.root.children)==0:
            nodes_to_expand.append(tree.root)
        else:
            for node in tree.nodes.values():
                if len(node.children)>0:
                    nodes_to_expand.extend(self._get_children_to_expand(node))

        expanded_nodes = set()
        batch_size = self.config.n_threads  # Use n_threads as batch size
        
        while nodes_to_expand and tree.total_nodes < self.config.max_nodes:

            # Before each batch, recalculate scores and propagate using minimax
            print("Clearing, recalculating, and repropagating node scores")
            self._clear_tree_scores(tree)
            self._analyze_current_tree_state(tree)

            # Collect a batch of nodes to expand
            batch_nodes: List[GameTreeNode] = []
            while len(batch_nodes) < batch_size and nodes_to_expand and tree.total_nodes < self.config.max_nodes:
                current_node = nodes_to_expand.popleft()
                if current_node.node_id not in expanded_nodes:
                    batch_nodes.append(current_node)
            
            if not batch_nodes:
                break
            
            print(f"\n   {len(expanded_nodes)} expanded, {len(batch_nodes)} in current batch, {len(nodes_to_expand)} nodes remain in queue")
            print(f"   Expanding batch of {len(batch_nodes)} nodes...")
            
            # Expand nodes in batch
            tree.expand_nodes_batch(batch_nodes, self.gemini_client, self.config.max_branches_per_node)
            
            # Mark nodes as expanded and process results
            for node in batch_nodes:
                expanded_nodes.add(node.node_id)
                children_to_expand = self._get_children_to_expand(node)
                nodes_to_expand.extend(children_to_expand)
                viable_children_added += len(children_to_expand)

            # After each batch, recalculate scores and propagate using minimax
            print("Clearing, recalculating, and repropagating node scores")
            self._clear_tree_scores(tree)
            self._analyze_current_tree_state(tree)

            # Save tree after every batch expansion
            self.tree_manager.save_tree(tree, f"{self.matchup_name}_{starting_player}")
    
    def _load_tree(self, tree_name: str) -> Optional[GameTree]:
        """Load a game tree from file."""
        try:
            tree = self.tree_manager.load_tree(tree_name)
            return tree
        except Exception as e:
            print(f"   Error loading tree: {e}")
            return None
    
    def _clear_tree_scores(self, tree: GameTree):
        """Clear all scores from all nodes in the tree."""
        for node_id in tree.nodes:
            node = tree.nodes[node_id]
            node.score = None
    
    def _analyze_current_tree_state(self, tree: GameTree):
        """Analyze the current tree state by assigning scores and propagating with minimax."""
        # Assign outcomes to loop nodes
        for node in tree.terminal_nodes:
            if node.is_loop and node.outcome is None:
                node.outcome, node.loop_hp_totals = self._determine_loop_outcome(node)
                print(f"Loop outcome ({node.loop_type}): {node.outcome}")
        
        # Assign scores to terminal nodes
        for node in tree.terminal_nodes:
            if node.score is None:
                node.score = self._assign_terminal_score(node)
        
        # Assign scores and outcomes to transposition nodes
        for node in tree.terminal_nodes:
            if node.is_transposition and node.score is None:
                id = node.transposition_target_id
                # Find the node with the same transposition_target_id and use its score
                for other_node in tree.terminal_nodes:
                    if other_node.node_id == id and other_node.score is not None:
                        node.score = other_node.score
                        node.outcome = other_node.outcome
                        break

        # Propagate scores up the tree using alpha-beta minimax
        self._minimax(tree.root, float('-inf'), float('inf'))
    
    def _analyze_tree(self, tree: GameTree) -> Dict:
        """Final analysis of a completed tree to determine optimal play."""
        # Ensure all terminal nodes are analyzed
        self._analyze_current_tree_state(tree)
        
        # Find the optimal path
        optimal_path = self._find_optimal_path(tree.root)
        
        return {
            'tree': tree,
            'optimal_path': optimal_path,
            'root_score': tree.root.score
        }
    
    def _determine_loop_outcome(self, node: GameTreeNode) -> tuple[str, list[tuple[int, int]]]:
        """Determine the outcome of a loop node."""
        if node.loop_type == "exact":
            return "draw", []
        elif node.loop_type == "near":
            current_node = node
            p1_hp = [current_node.game_state.player1_state.life]
            p2_hp = [current_node.game_state.player2_state.life]
            print(f"Loop detected at node {node.node_id}, loop target: {node.loop_target_id}")
            while current_node.node_id != node.loop_target_id:
                if current_node.parent is None:
                    raise ValueError("Loop detected but loop target not in lineage")
                current_node = current_node.parent
                p1_hp.append(current_node.game_state.player1_state.life)
                p2_hp.append(current_node.game_state.player2_state.life)
            p1_damage_increments = [p1_hp[i] - p1_hp[i+1] for i in range(len(p1_hp) - 1)]
            p2_damage_increments = [p2_hp[i] - p2_hp[i+1] for i in range(len(p2_hp) - 1)]
            p1_hp_total = p1_hp[0]
            p2_hp_total = p2_hp[0]
            loop_life_totals = [(p1_hp_total, p2_hp_total)]
            print(f"Damage incremenets - p1: {p1_damage_increments} | p2: {p2_damage_increments}")
            for i in range(1000):
                ii = i % len(p1_damage_increments)
                p1_hp_total += p1_damage_increments[ii]
                p2_hp_total += p2_damage_increments[ii]
                loop_life_totals.append((p1_hp_total, p2_hp_total))
                if i < 10:
                    print(f"p1: {p1_hp_total} | p2: {p2_hp_total}")
                if p1_hp_total <= 0 or p2_hp_total <= 0:
                    break
            p1_dead = p1_hp_total <= 0
            p2_dead = p2_hp_total <= 0
            return "player2" if (p1_dead and not p2_dead) else "player1" if (p2_dead and not p1_dead) else "draw", loop_life_totals
        else:
            return "draw", []

    def _assign_terminal_score(self, node: GameTreeNode) -> float:
        """Assign a score to a terminal node."""
        if node.is_transposition:
            # Transpositions are assigned later
            return None
        elif node.outcome == "player1":
            return 1.0
        elif node.outcome == "player2":
            return -1.0
        else:  # draw
            return 0.0
    
    def _minimax(self, node: GameTreeNode, alpha: float = float('-inf'), beta: float = float('inf')):
        """Apply minimax algorithm with alpha-beta pruning to propagate scores."""
        
        if node.is_terminal:
            return node.score
        
        current_player = node.game_state.player_to_act
        n_children = len(node.children)
        
        if current_player == "player1":
            # Player 1 wants to maximize the score
            max_eval = float('-inf')
            for i_child in range(n_children):
                child = node.children[i_child]
                eval_score = self._minimax(child, alpha, beta)
                if eval_score is not None:
                    max_eval = max(max_eval, eval_score)
                    alpha = max(alpha, eval_score)
                    # Alpha-beta pruning
                    if beta <= alpha:
                        # Mark all further nodes as skipped by alpha beta pruning
                        for j in range(i_child + 1, n_children):
                            node.children[j].mark_alpha_beta_skip()
                        break
            node.score = max_eval if max_eval != float('-inf') else None
            return node.score
        else:
            # Player 2 wants to minimize the score
            min_eval = float('inf')
            for i_child in range(n_children):
                child = node.children[i_child]
                eval_score = self._minimax(child, alpha, beta)
                if eval_score is not None:
                    min_eval = min(min_eval, eval_score)
                    beta = min(beta, eval_score)
                    # Alpha-beta pruning
                    if beta <= alpha:
                        # Mark all further nodes as skipped by alpha beta pruning
                        for j in range(i_child + 1, n_children):
                            node.children[j].mark_alpha_beta_skip()
                        break
            node.score = min_eval if min_eval != float('inf') else None
            return node.score
    
    def _get_children_to_expand(self, node: GameTreeNode) -> List[GameTreeNode]:
        """Get the children that should be expanded."""
        if node.is_terminal or len(node.children) == 0 or node.depth+1 >= self.config.max_depth:
            return []

        # First filter by viability
        potential_children_to_expand = [child for child in node.children if child.viability >= self.config.viability_threshold]
        if len(potential_children_to_expand)==0:
            print("Node has children but none over viability threshold. Picking the most viable...")
            print([child.viability for child in node.children])
            max_viability = max([child.viability for child in node.children])
            for child in node.children:
                if child.viability==max_viability and not child.is_terminal:
                    potential_children_to_expand.append(child)

        # Then filter by alpha-beta bounds, grandchildren, and terminality
        children_to_expand = []
        for child in potential_children_to_expand:
            if not child.is_terminal and len(child.children)==0 and not child.alpha_beta_skip:
                children_to_expand.append(child)
                
        return children_to_expand
    
    def _find_optimal_path(self, node: GameTreeNode) -> List[GameTreeNode]:
        """Find the optimal path from root to terminal node."""
        path = [node]
        
        while not node.is_terminal and node.children:
            current_player = node.game_state.player_to_act
            
            if current_player == "player1":
                # Player 1 chooses child with maximum score
                best_child = max(node.children, key=lambda x: x.score if x.score is not None else float('-inf'))
            else:
                # Player 2 chooses child with minimum score
                best_child = min(node.children, key=lambda x: x.score if x.score is not None else float('inf'))
            
            if best_child.score is None:
                break
            
            path.append(best_child)
            node = best_child
        
        return path
    
    def _determine_overall_winner(self, p1_result: Dict, p2_result: Dict) -> tuple(str, float):
        """Determine the overall score out of WW, TT, LL, WL, WT, and TL."""
        p1_score = p1_result['root_score']
        p2_score = p2_result['root_score']
        if p1_score==1.0 and p2_score==1.0:
            return "WL", 1.0
        elif p1_score==1.0 and p2_score==-1.0:
            return "WW", 2.0
        elif p1_score==-1.0 and p2_score==1.0:
            return "LL", 0.0
        elif p1_score==1.0 and (p2_score is None or p2_score==0.0):
            return "WT", 1.5
        elif (p1_score is None or p1_score==0.0) and (p2_score is None or p2_score==0.0):
            return "TT", 1.0
        elif (p1_score is None or p1_score==0.0) and p2_score==1.0:
            return "TL", 0.5
        else:
            raise ValueError(f"Invalid scores: p1_score={p1_score}, p2_score={p2_score}")

    
    def _print_results(self, result: AnalysisResult):
        """Print the analysis results."""
        print("\n" + "="*60)
        print("ANALYSIS RESULTS")
        print("="*60)
        
        print(f"\nPlayer 1 cards: {result.player1_cards}")
        print(f"Player 2 cards: {result.player2_cards}")
        print(f"\nOutcome: {result.outcome_string} ({result.outcome_float})")
        print(f"Analysis time: {result.analysis_time:.2f} seconds")
        print(f"Total nodes analyzed: {result.total_nodes}")
        print(f"Maximum tree depth: {result.max_depth}")
        
        print(f"\nTerminal nodes by outcome:")
        for outcome, count in result.terminal_nodes_by_outcome.items():
            print(f"   {outcome}: {count}")
        
        print()
        print("*" * 60)
        print(f"\nOptimal play path with first player starting ({len(result.optimal_path_p1)} nodes):")
        for i, node in enumerate(result.optimal_path_p1):
            if node.decision:
                print(f"         -> {node.decision}\n")
            print(f"   {i+1}. ({node.game_state.player1_state.life}:{node.game_state.player2_state.life}) {node.game_state.turn_player}'s turn, {node.game_state.phase}, {node.game_state.player_to_act} to act")
            
            if node.is_terminal:
                if node.is_loop:
                    print(f"          -> Loop detected ({node.loop_type})")
                    if (node.outcome!="draw"):
                        print("           Hp totals:")
                        for hp_total in node.loop_hp_totals:
                            print(f"             P1: {hp_total[0]}, P2: {hp_total[1]}")
                elif node.is_transposition:
                    print(f"          -> Transposition to node {node.transposition_target_id[:8]}...")
                else:
                    print(f"          -> {node.outcome}")
                break
        
        print()
        print("*" * 60)
        print(f"\nOptimal play path with second player starting ({len(result.optimal_path_p2)} nodes):")
        for i, node in enumerate(result.optimal_path_p2):
            if node.decision:
                print(f"         -> {node.decision}\n")
            print(f"   {i+1}. ({node.game_state.player1_state.life}:{node.game_state.player2_state.life}) {node.game_state.turn_player}'s turn, {node.game_state.phase}, {node.game_state.player_to_act} to act")
            
            if node.is_terminal:
                if node.is_loop:
                    print(f"          -> Loop detected ({node.loop_type})")
                    if (node.outcome!="draw"):
                        print("           Hp totals:")
                        for hp_total in node.loop_hp_totals:
                            print(f"             P1: {hp_total[0]}, P2: {hp_total[1]}")
                elif node.is_transposition:
                    print(f"          -> Transposition to node {node.transposition_target_id[:8]}...")
                else:
                    print(f"          -> {node.outcome}")
                break

        print()
        print("*" * 60)
        print(f"\nTo visualize the trees, run:")
        print(f"  python visualize_tree.py '{self.matchup_name.replace(' ', '_')}_player1'")
        print(f"  python visualize_tree.py '{self.matchup_name.replace(' ', '_')}_player2'")
        
        print("\n" + "="*60)

#!/usr/bin/env python3
"""
Visual display system for 3CardSeer game tree and game state visualization.
Uses tkinter for GUI and PIL for image handling.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import requests
from PIL import Image, ImageTk
import io
from typing import Dict, List, Optional, Any, Tuple
import math
import threading
from dataclasses import dataclass

from src.game_tree import GameTree, GameTreeNode
from src.game_state import GameState
from src.card_data import Card
from src.gemini_client import GeminiClient


@dataclass
class VisualNode:
    """Represents a visual node in the tree display."""
    node_id: str
    x: float
    y: float
    radius: float = 20
    canvas_id: Optional[int] = None
    expand_button_id: Optional[int] = None
    game_tree_node: Optional[GameTreeNode] = None


class GameTreeWindow:
    """Window for displaying the game tree."""
    
    def __init__(self, game_tree: GameTree, on_node_click_callback):
        self.window = tk.Tk()  # Make this the root window
        self.window.title("Game Tree Visualization")
        self.window.geometry("600x800")
        
        self.game_tree = game_tree
        self.on_node_click = on_node_click_callback
        self.visual_nodes: Dict[str, VisualNode] = {}
        self.selected_node: Optional[VisualNode] = None
        self.hover_node: Optional[VisualNode] = None
        self.expanding_nodes: set = set()
        self.tooltip_window: Optional[tk.Toplevel] = None
        self.state_window: Optional[GameStateWindow] = None
        self.transposition_line_id: Optional[int] = None
        self.loop_line_id: Optional[int] = None
        self.loop_text_id: Optional[int] = None
        
        self._setup_ui()
        self._draw_tree()
        
        # Cleanup tooltip when window closes
        self.window.bind("<Destroy>", lambda e: self._hide_tooltip())
        
        # Handle window close event
        self.window.protocol("WM_DELETE_WINDOW", self._on_window_close)
        
    def _setup_ui(self):
        """Set up the user interface with clean layout."""
        # Main container
        main_container = ttk.Frame(self.window)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Title
        title_label = ttk.Label(main_container, text="Game Tree Visualization", 
                               font=("Arial", 14, "bold"))
        title_label.pack(pady=(0, 10))
        
        # Canvas container with scrollbars
        canvas_container = ttk.Frame(main_container)
        canvas_container.pack(fill=tk.BOTH, expand=True)
        
        # Create canvas
        self.canvas = tk.Canvas(canvas_container, bg="gray", highlightthickness=1)
        
        # Create scrollbars
        v_scrollbar = ttk.Scrollbar(canvas_container, orient=tk.VERTICAL, 
                                 command=self.canvas.yview)
        h_scrollbar = ttk.Scrollbar(canvas_container, orient=tk.HORIZONTAL, 
                                 command=self.canvas.xview)
        
        # Configure canvas scroll region
        self.canvas.configure(yscrollcommand=v_scrollbar.set, 
                          xscrollcommand=h_scrollbar.set)
        
        # Grid layout for canvas and scrollbars
        self.canvas.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        # Configure grid weights
        canvas_container.grid_rowconfigure(0, weight=1)
        canvas_container.grid_columnconfigure(0, weight=1)
        
        # Bind events
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Motion>", self._on_mouse_motion)
        
        # Bind mouse wheel events for scrolling
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)        # Windows/Linux
        self.canvas.bind("<TouchpadScroll>", self._on_mousewheel)    # macOS
        self.canvas.bind("<Button-4>", self._on_mousewheel)          # Linux scroll up
        self.canvas.bind("<Button-5>", self._on_mousewheel)          # Linux scroll down
        
    def _draw_tree(self):
        """Draw the game tree on the canvas."""
        self.canvas.delete("all")
        self.visual_nodes.clear()
        
        if not self.game_tree or not self.game_tree.root:
            return
        
        # Calculate tree layout
        self._calculate_tree_layout()
        
        # Update scroll region
        self._update_scroll_region()
        
        # Draw edges first (so they appear behind nodes)
        self._draw_edges()
        
        # Draw nodes
        self._draw_nodes()
        
    def _calculate_tree_layout(self):
        """Calculate positions for all nodes in the tree."""
        # Simple tree layout algorithm
        level_height = 100
        min_node_spacing = 60
        
        # Group nodes by depth
        nodes_by_depth = {}
        max_nodes_at_depth = 0
        
        def collect_nodes_by_depth(node: GameTreeNode):
            depth = node.depth
            if depth not in nodes_by_depth:
                nodes_by_depth[depth] = []
            nodes_by_depth[depth].append(node)
            nonlocal max_nodes_at_depth
            max_nodes_at_depth = max(max_nodes_at_depth, len(nodes_by_depth[depth]))
            
            for child in node.children:
                collect_nodes_by_depth(child)
        
        collect_nodes_by_depth(self.game_tree.root)
        
        # Update canvas to ensure it has proper dimensions
        self.canvas.update_idletasks()
        
        # Calculate canvas dimensions - match actual canvas size
        canvas_width = self.canvas.winfo_width()
        canvas_height = max(600, len(nodes_by_depth) * level_height + 100)
                
        # Position nodes with better centering
        for depth, nodes in nodes_by_depth.items():
            y = 100 + depth * level_height
            num_nodes = len(nodes)
            
            # Adjust spacing based on number of nodes
            if num_nodes == 1:
                x = canvas_width / 2
                visual_node = VisualNode(
                    node_id=nodes[0].node_id,
                    x=x,
                    y=y,
                    game_tree_node=nodes[0]
                )
                self.visual_nodes[nodes[0].node_id] = visual_node
            else:
                # Dynamic spacing based on canvas width with min/max constraints
                available_width = canvas_width - 100  # Leave margins
                ideal_spacing = available_width / (num_nodes - 1)
                spacing = max(50, min(ideal_spacing, 80))  # Min 50px, Max 80px spacing
                total_width = (num_nodes - 1) * spacing
                start_x = (canvas_width - total_width) / 2
                
                for i, node in enumerate(nodes):
                    x = start_x + i * spacing
                    
                    visual_node = VisualNode(
                        node_id=node.node_id,
                        x=x,
                        y=y,
                        game_tree_node=node
                    )
                    self.visual_nodes[node.node_id] = visual_node
        
    def _draw_edges(self):
        """Draw edges between parent and child nodes."""
        # Create a set of node IDs that are in the optimal path for quick lookup
        optimal_path_nodes = set()
        if self.game_tree.optimal_path:
            optimal_path_nodes = {node.node_id for node in self.game_tree.optimal_path}
        
        for _, visual_node in self.visual_nodes.items():
            game_tree_node = visual_node.game_tree_node
            if game_tree_node and game_tree_node.parent:
                parent_visual = self.visual_nodes.get(game_tree_node.parent.node_id)
                if parent_visual:
                    # Check if this edge is part of the optimal path
                    is_optimal = (game_tree_node.node_id in optimal_path_nodes and 
                                 game_tree_node.parent.node_id in optimal_path_nodes)
                    
                    if is_optimal:
                        # Draw optimal path edges as thick green lines
                        self.canvas.create_line(
                            parent_visual.x, parent_visual.y,
                            visual_node.x, visual_node.y,
                            fill="green", width=4, tags="edge"
                        )
                    else:
                        # Draw normal edges as black lines
                        self.canvas.create_line(
                            parent_visual.x, parent_visual.y,
                            visual_node.x, visual_node.y,
                            fill="black", width=2, tags="edge"
                        )
    
    def _draw_nodes(self):
        """Draw all nodes on the canvas."""
        for _, visual_node in self.visual_nodes.items():
            self._draw_node(visual_node)
    
    def _draw_node(self, visual_node: VisualNode):
        """Draw a single node."""
        x, y = visual_node.x, visual_node.y
        
        # Determine radius based on expansion state
        base_radius = 20
        if visual_node.game_tree_node and len(visual_node.game_tree_node.children) > 0:
            # Expanded nodes are slightly bigger
            radius = base_radius + 5
        else:
            # Unexpanded nodes are slightly smaller
            radius = base_radius - 3
        
        # Determine node color based on state
        color = "lightblue"  # Default color
        if visual_node.game_tree_node:
            # Priority 0: Expansion state
            if visual_node.node_id in self.expanding_nodes:
                color = "#006400"  # Dark green
            # Priority 1: Loop state (highest priority after expansion)
            elif visual_node.game_tree_node.is_loop:
                if visual_node.game_tree_node.loop_type == "exact":
                    color = "orange"  # Orange for exact loops
                elif visual_node.game_tree_node.loop_type == "near":
                    color = "gold"  # Gold for near loops
                else:
                    color = "orange"  # Default orange for unknown loop types
            # Priority 2: Transposition state
            elif visual_node.game_tree_node.is_transposition:
                color = "grey"  # Grey for transposition nodes
            # Priority 3: Selection/hover states
            elif visual_node == self.selected_node:
                # Selection color based on player to act
                player_to_act = visual_node.game_tree_node.game_state.player_to_act
                if player_to_act == "player1":
                    color = "#8B0000"  # Dark red
                elif player_to_act == "player2":
                    color = "#00008B"  # Dark blue
                else:
                    color = "#4B0082"  # Indigo fallback
            elif visual_node == self.hover_node:
                # Hover color based on player to act
                player_to_act = visual_node.game_tree_node.game_state.player_to_act
                if player_to_act == "player1":
                    color = "#FF69B4"  # Hot pink/darker red
                elif player_to_act == "player2":
                    color = "#4682B4"  # Steel blue/darker blue
                else:
                    color = "#87CEEB"  # Sky blue fallback
            # Priority 4: Terminal states
            elif visual_node.game_tree_node.is_terminal:
                if visual_node.game_tree_node.outcome == "player1":
                    color = "lightgreen"
                elif visual_node.game_tree_node.outcome == "player2":
                    color = "lightcoral"
                else:
                    color = "lightyellow"
            # Priority 5: Player to act
            else:
                player_to_act = visual_node.game_tree_node.game_state.player_to_act
                if player_to_act == "player1":
                    color = "#FFB6C1"  # Light red/pink
                elif player_to_act == "player2":
                    color = "#ADD8E6"  # Light blue
        
        # Draw node circle
        canvas_id = self.canvas.create_oval(
            x - radius, y - radius,
            x + radius, y + radius,
            fill=color, outline="black", width=2,
            tags=("node", f"node_{visual_node.node_id}")
        )
        visual_node.canvas_id = canvas_id
                
        # Draw expand button if node has no children (can be expanded) and is not terminal
        if visual_node.game_tree_node and not visual_node.game_tree_node.is_terminal and len(visual_node.game_tree_node.children) == 0:
            button_size = 8
            button_x = x + radius - 5
            button_y = y - radius + 5
            
            expand_button_id = self.canvas.create_rectangle(
                button_x - button_size, button_y - button_size,
                button_x + button_size, button_y + button_size,
                fill="orange", outline="darkorange", width=1,
                tags=("expansion_button", f"expand_{visual_node.node_id}")
            )
            visual_node.expand_button_id = expand_button_id
            
            # Add + sign
            self.canvas.create_text(
                button_x, button_y, text="+", font=("Arial", 8, "bold"),
                fill="white", tags=("expand_text", f"expand_text_{visual_node.node_id}")
            )
        
        # Draw viability score if available
        if visual_node.game_tree_node and visual_node.game_tree_node.viability is not None:
            viability_score = visual_node.game_tree_node.viability
            # Scale font size based on node radius
            base_font_size = 10
            if visual_node.game_tree_node and len(visual_node.game_tree_node.children) > 0:
                # Larger font for expanded nodes
                font_size = base_font_size + 2
            else:
                # Smaller font for unexpanded nodes
                font_size = base_font_size - 2
            
            # Further adjust based on viability score value
            if viability_score <= 4:
                font_size = max(6, font_size - 2)
            elif viability_score >= 8:
                font_size = min(14, font_size + 2)
            
            # Position text in center of node
            self.canvas.create_text(
                x, y, text=str(int(viability_score)), 
                font=("Arial", font_size, "bold"),
                fill="white", tags=("viability_text", f"viability_{visual_node.node_id}")
            )
    
    def _on_canvas_click(self, event):
        """Handle canvas click events with improved detection."""
        # Find all items at click position
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        clicked_items = self.canvas.find_overlapping(canvas_x-2, canvas_y-2, canvas_x+2, canvas_y+2)
        
        # Check for expand button clicks first (higher priority)
        for item in clicked_items:
            tags = self.canvas.gettags(item)
            for tag in tags:
                if tag.startswith("expand_"):
                    node_id = tag.replace("expand_", "")
                    print(f"Clicked on expand button for node {node_id}")
                    self._on_expand_click(node_id)
                    return
        
        # Check for node clicks
        for item in clicked_items:
            tags = self.canvas.gettags(item)
            for tag in tags:
                if tag.startswith("node_"):
                    node_id = tag.replace("node_", "")
                    self._on_node_click(node_id)
                    return
    
    def _draw_transposition_line(self, from_visual_node: VisualNode, to_visual_node: VisualNode):
        """Draw a dotted line connecting two transposition nodes."""
        if self.transposition_line_id:
            self.canvas.delete(self.transposition_line_id)
            self.transposition_line_id = None
        
        # Draw dotted line
        self.transposition_line_id = self.canvas.create_line(
            from_visual_node.x, from_visual_node.y,
            to_visual_node.x, to_visual_node.y,
            fill="purple", width=2, dash=(5, 5), tags="transposition_line"
        )
        # Move line to back so it appears behind other elements
        self.canvas.tag_lower("transposition_line")
    
    def _hide_transposition_line(self):
        """Hide the transposition line."""
        if self.transposition_line_id:
            self.canvas.delete(self.transposition_line_id)
            self.transposition_line_id = None
    
    def _draw_loop_line(self, from_visual_node: VisualNode, to_visual_node: VisualNode):
        """Draw a curved dotted line connecting two loop nodes."""
        if self.loop_line_id:
            self.canvas.delete(self.loop_line_id)
            self.loop_line_id = None
        if self.loop_text_id:
            self.canvas.delete(self.loop_text_id)
            self.loop_text_id = None
        
        # Calculate control points for a curved line
        x1, y1 = from_visual_node.x, from_visual_node.y
        x2, y2 = to_visual_node.x, to_visual_node.y
        
        # Calculate midpoint and offset for curve
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2
        
        # Create a perpendicular offset for the curve
        dx = x2 - x1
        dy = y2 - y1
        length = math.sqrt(dx**2 + dy**2)
        if length > 0:
            # Normalize and rotate 90 degrees
            perp_x = -dy / length
            perp_y = dx / length
            # Apply offset (curve amount proportional to distance)
            curve_offset = min(100, length / 2)
            control_x = mid_x - perp_x * curve_offset
            control_y = mid_y - perp_y * curve_offset
        else:
            control_x, control_y = mid_x, mid_y
        
        # Draw curved dotted line using smooth bezier curve approximation
        points = []
        steps = 20
        for i in range(steps + 1):
            t = i / steps
            # Quadratic bezier curve formula
            bx = (1-t)**2 * x1 + 2*(1-t)*t * control_x + t**2 * x2
            by = (1-t)**2 * y1 + 2*(1-t)*t * control_y + t**2 * y2
            points.extend([bx, by])
        
        self.loop_line_id = self.canvas.create_line(
            points,
            fill="red", width=2, dash=(3, 3), tags="loop_line"
        )
        
        # Add text for near loops showing life differential
        if (from_visual_node.game_tree_node and 
            from_visual_node.game_tree_node.loop_type == "near" and
            to_visual_node.game_tree_node):
            
            # Calculate life differentials
            from_state = from_visual_node.game_tree_node.game_state
            to_state = to_visual_node.game_tree_node.game_state
            
            p1_diff = from_state.player1_state.life - to_state.player1_state.life
            p2_diff = from_state.player2_state.life - to_state.player2_state.life
            
            # Format differential text
            diff_text = f"P1: {p1_diff:+d} | P2: {p2_diff:+d}"
            
            # Position text at the control point (peak of the curve)
            self.loop_text_id = self.canvas.create_text(
                control_x, control_y,
                text=diff_text,
                font=("Arial", 8, "bold"),
                fill="darkred",
                tags="loop_text"
            )
        
        # Move line and text to back so they appear behind other elements
        self.canvas.tag_lower("loop_line")
        if self.loop_text_id:
            self.canvas.tag_lower("loop_text")
    
    def _hide_loop_line(self):
        """Hide the loop line."""
        if self.loop_line_id:
            self.canvas.delete(self.loop_line_id)
            self.loop_line_id = None
        if self.loop_text_id:
            self.canvas.delete(self.loop_text_id)
            self.loop_text_id = None
    
    def _on_mouse_motion(self, event):
        """Handle mouse motion for hover effects and tooltips."""
        # Find node under cursor
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        items = self.canvas.find_overlapping(canvas_x-2, canvas_y-2, canvas_x+2, canvas_y+2)
        
        hover_node = None
        for item in items:
            tags = self.canvas.gettags(item)
            for tag in tags:
                if tag.startswith("node_"):
                    node_id = tag.replace("node_", "")
                    hover_node = self.visual_nodes.get(node_id)
                    break
            if hover_node:
                break
        
        # Update hover state if changed
        if hover_node != self.hover_node:
            # Remove old hover effect
            if self.hover_node:
                old_hover = self.hover_node
                self.hover_node = None
                self._draw_node(old_hover)
                # Hide transposition line if leaving a transposition node
                if old_hover.game_tree_node and old_hover.game_tree_node.is_transposition:
                    self._hide_transposition_line()
                # Hide loop line if leaving a loop node
                if old_hover.game_tree_node and old_hover.game_tree_node.is_loop:
                    self._hide_loop_line()
            
            # Add new hover effect
            self.hover_node = hover_node
            if hover_node:
                self._draw_node(hover_node)
                self._show_tooltip(event, hover_node)
                
                # Show transposition line if hovering over a transposition node
                if hover_node.game_tree_node and hover_node.game_tree_node.is_transposition:
                    target_node_id = hover_node.game_tree_node.transposition_target_id
                    if target_node_id and target_node_id in self.visual_nodes:
                        target_visual_node = self.visual_nodes[target_node_id]
                        self._draw_transposition_line(hover_node, target_visual_node)
                
                # Show loop line if hovering over a loop node
                if hover_node.game_tree_node and hover_node.game_tree_node.is_loop:
                    target_node_id = hover_node.game_tree_node.loop_target_id
                    if target_node_id and target_node_id in self.visual_nodes:
                        target_visual_node = self.visual_nodes[target_node_id]
                        self._draw_loop_line(hover_node, target_visual_node)
            else:
                self._hide_tooltip()
                self._hide_transposition_line()
                self._hide_loop_line()
    
    def _on_mousewheel(self, event):
        """Handle mouse wheel scrolling."""
        # Different platforms use different event attributes
        if event.delta:
            # Windows/Mac: event.delta contains scroll amount
            scroll_amount = (event.delta / 120.)
        else:
            # Linux: event.num contains button number
            if event.num == 4:
                scroll_amount = -1  # Scroll up
            elif event.num == 5:
                scroll_amount = 1   # Scroll down
            else:
                return
        
        # Scroll the canvas vertically
        if abs(scroll_amount) < 1:
            return
        if abs(scroll_amount) > 1:
            scroll_amount = 1 if scroll_amount > 0 else -1
        self.canvas.yview_scroll(scroll_amount, "units")
    
    def _show_tooltip(self, event, visual_node: VisualNode):
        """Show tooltip with decision text."""
        self._hide_tooltip()  # Remove any existing tooltip
        
        if not visual_node.game_tree_node:
            return
        
        # Create tooltip window
        self.tooltip_window = tk.Toplevel(self.window)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
        
        # Format tooltip text
        tooltip_text = ""
        if visual_node.game_tree_node.decision:
            tooltip_text = visual_node.game_tree_node.decision
        else:
            tooltip_text = "Initial state"
        
        # Add loop information if applicable
        if visual_node.game_tree_node.is_loop:
            loop_type = visual_node.game_tree_node.loop_type
            if loop_type == "exact":
                tooltip_text += "\n🔄 Exact loop (same game state)"
            elif loop_type == "near":
                tooltip_text += "\n🔄 Near loop (same state, different life)"
            else:
                tooltip_text += "\n🔄 Loop detected"
        
        # Add transposition information if applicable
        elif visual_node.game_tree_node.is_transposition:
            tooltip_text += "\n🔄 Transposition node"
            if visual_node.game_tree_node.transposition_target_id:
                tooltip_text += f" (links to node {visual_node.game_tree_node.transposition_target_id[:8]}...)"
        
        label = ttk.Label(
            self.tooltip_window, 
            text=tooltip_text, 
            background="lightyellow", 
            relief=tk.FLAT,
            borderwidth=1,
            font=("Arial", 9),
            wraplength=200
        )
        label.pack(padx=5, pady=3)
    
    def _hide_tooltip(self):
        """Hide tooltip."""
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None
    
    def _on_node_click(self, node_id: str):
        """Handle node click."""
        old_selected = self.selected_node
        visual_node = self.visual_nodes.get(node_id)
        if visual_node and visual_node.game_tree_node:
            # Update selection
            self.selected_node = visual_node
            
            if old_selected:
                self._draw_node(old_selected)  # Redraw to remove selection

            self._draw_node(visual_node)  # Redraw to show selection
            
            # Notify callback
            if self.on_node_click:
                self.on_node_click(visual_node.game_tree_node)
    
    def _on_expand_click(self, node_id: str):
        """Handle expand button click."""
        visual_node = self.visual_nodes.get(node_id)
        if visual_node and visual_node.game_tree_node:
            # Add to expanding set and redraw to show dark green color
            self.expanding_nodes.add(node_id)
            self._draw_node(visual_node)
            self.window.update()  # Force immediate redraw
            
            # Trigger expansion (this will be handled by the main application)
            if self.on_node_click:
                self.on_node_click(visual_node.game_tree_node, expand=True)
    
    def _on_canvas_resize(self, event):
        """Handle canvas resize and redraw tree."""
        # Redraw tree with new canvas dimensions
        self._draw_tree()
    
    def _update_scroll_region(self):
        """Update the canvas scroll region."""
        box = self.canvas.bbox("all")
        box_with_zero = (0, 0, box[2]+75, box[3]+75) if box else None
        self.canvas.configure(scrollregion=box_with_zero)
    
    def refresh_tree(self):
        """Refresh the tree display."""
        self._draw_tree()
    
    def _on_window_close(self):
        """Handle window close event."""
        self._hide_tooltip()
        
        # Close state window if open
        if self.state_window and hasattr(self.state_window, 'window'):
            self.state_window.window.destroy()
        
        # Destroy the main window
        self.window.destroy()
    
    def open_state_window(self):
        """Open the game state window."""
        if self.state_window and hasattr(self.state_window, 'window'):
            self.state_window.window.lift()
            return
        
        self.state_window = GameStateWindow(self.window, on_close_callback=self._on_state_window_closed)
        
        # Show initial state if available
        if self.game_tree and self.game_tree.root:
            self.state_window.update_game_tree_node(self.game_tree.root)
    
    def _on_state_window_closed(self):
        """Handle state window close event."""
        # Deselect the current node
        if self.selected_node:
            self._draw_node(self.selected_node)  # Redraw to remove selection
            self.selected_node = None
        
        # Clear the state window reference
        self.state_window = None

        # Refresh the tree to show updated state
        self.refresh_tree()


class GameStateWindow:
    """Window for displaying the game state with card images and node information."""
    
    def __init__(self, parent, on_close_callback=None):
        self.window = tk.Toplevel(parent)
        self.window.title("Game State Visualization")
        self.window.geometry("800x1000")
        
        self.on_close_callback = on_close_callback
        
        self.current_game_tree_node: Optional[GameTreeNode] = None
        self.card_images: Dict[str, Image.Image] = {}
        self.photo_image_cache: Dict[str, ImageTk.PhotoImage] = {}
        
        self._setup_ui()
        
        # Handle window close event
        self.window.protocol("WM_DELETE_WINDOW", self._on_window_close)
        
    def _setup_ui(self):
        """Set up the user interface."""
        # Main frame
        main_frame = ttk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Title
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        
        self.title_label = ttk.Label(title_frame, text="Game State", font=("Arial", 14, "bold"))
        self.title_label.pack(side=tk.LEFT)
        
        # Game info
        self.info_label = ttk.Label(title_frame, text="", font=("Arial", 10))
        self.info_label.pack(side=tk.RIGHT)
        
        # Node information frame
        self.node_info_frame = ttk.LabelFrame(main_frame, text="Node Information", padding="10")
        self.node_info_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        
        # Decision text
        self.decision_text = tk.Text(self.node_info_frame, height=6, wrap=tk.WORD, font=("Arial", 10, "bold"))
        self.decision_text.pack(side=tk.TOP, fill=tk.X, pady=(0, 5))
        
        # Viability and explanation frame
        self.viability_frame = ttk.Frame(self.node_info_frame)
        self.viability_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 5))
        
        self.viability_label = ttk.Label(self.viability_frame, text="", font=("Arial", 10))
        self.viability_label.pack(side=tk.LEFT)
        
        # Explanation text
        self.explanation_text = tk.Text(self.node_info_frame, height=4, wrap=tk.WORD, font=("Arial", 9))
        self.explanation_text.pack(side=tk.TOP, fill=tk.X, pady=(5, 0))
        
        # Node status frame
        self.status_frame = ttk.Frame(self.node_info_frame)
        self.status_frame.pack(side=tk.TOP, fill=tk.X, pady=(5, 0))
        
        self.status_label = ttk.Label(self.status_frame, text="", font=("Arial", 9, "italic"))
        self.status_label.pack(side=tk.LEFT)
        
        # Game state display
        self.state_frame = ttk.Frame(main_frame)
        self.state_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create player areas
        self._create_player_areas()
        
    def _create_player_areas(self):
        """Create display areas for both players."""
        # Player 1 area (top)
        self.p1_frame = ttk.LabelFrame(self.state_frame, text="Player 1", padding="10")
        self.p1_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 5))
        
        self.p1_info = ttk.Label(self.p1_frame, text="", font=("Arial", 10))
        self.p1_info.pack(side=tk.TOP, fill=tk.X, pady=(0, 5))
        
        self.p1_battlefield_frame = ttk.Frame(self.p1_frame)
        self.p1_battlefield_frame.pack(side=tk.TOP, fill=tk.X, pady=2)
        
        # Player 2 area (bottom)
        self.p2_frame = ttk.LabelFrame(self.state_frame, text="Player 2", padding="10")
        self.p2_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(5, 0))
        
        self.p2_info = ttk.Label(self.p2_frame, text="", font=("Arial", 10))
        self.p2_info.pack(side=tk.TOP, fill=tk.X, pady=(0, 5))
        
        self.p2_battlefield_frame = ttk.Frame(self.p2_frame)
        self.p2_battlefield_frame.pack(side=tk.TOP, fill=tk.X, pady=2)
    
    def update_game_tree_node(self, game_tree_node: GameTreeNode):
        """Update the displayed game tree node and its game state."""
        self.current_game_tree_node = game_tree_node
        game_state = game_tree_node.game_state

        print("Game tree node:")
        print(f"  Decision: {game_tree_node.decision}")
        print(f"  Viability: {game_tree_node.viability}")
        print(f"  Explanation: {game_tree_node.explanation}")
        print(f"  Is loop: {game_tree_node.is_loop}")
        print(f"  Loop type: {game_tree_node.loop_type}")
        print(f"  Is transposition: {game_tree_node.is_transposition}")
        print("Game state")
        print(game_state.to_dict())        
        
        # Update title and info
        self.title_label.config(text=f"Game State - Turn {game_state.turn_counter}")
        self.info_label.config(
            text=f"Turn Player: {game_state.turn_player} | "
                 f"Player to Act: {game_state.player_to_act} | "
                 f"Phase: {game_state.phase.value}"
        )
        
        # Update node information
        self.decision_text.delete('1.0', tk.END)
        if game_tree_node.decision:
            self.decision_text.insert('1.0', f"Decision: {game_tree_node.decision}")
        else:
            self.decision_text.insert('1.0', "Decision: Initial state")
        
        # Update viability
        if game_tree_node.viability is not None:
            self.viability_label.config(text=f"Viability: {game_tree_node.viability}/10")
        else:
            self.viability_label.config(text="Viability: Not evaluated")
        
        # Update explanation
        self.explanation_text.delete('1.0', tk.END)
        if game_tree_node.explanation:
            self.explanation_text.insert('1.0', game_tree_node.explanation)
        else:
            self.explanation_text.insert('1.0', "No explanation available.")
        
        # Update node status
        status_parts = []

        # Outcome
        if game_tree_node.outcome:
            status_parts.append(f"Outcome: {game_tree_node.outcome}")
        
        # Score
        if game_tree_node.score is not None:
            status_parts.append(f"Score: {game_tree_node.score:.1f}")
        
        # Terminal status
        if game_tree_node.is_terminal:
            status_parts.append("Terminal")
        
        # Loop status
        if game_tree_node.is_loop:
            loop_type = game_tree_node.loop_type or "Unknown"
            status_parts.append(f"Loop ({loop_type})")
            if game_tree_node.loop_target_id:
                status_parts.append(f"Target: {game_tree_node.loop_target_id[:8]}...")
        
        # Transposition status
        if game_tree_node.is_transposition:
            status_parts.append("Transposition")
            if game_tree_node.transposition_target_id:
                status_parts.append(f"Target: {game_tree_node.transposition_target_id[:8]}...")
        
        # Expanded status
        if len(game_tree_node.children) > 0:
            status_parts.append("Expanded")
        else:
            status_parts.append("Not Expanded")
        
        # Set status text
        status_text = " | ".join(status_parts)
        
        self.status_label.config(text=status_text)
        
        # Clear current displays
        self._clear_frame(self.p1_battlefield_frame)
        self._clear_frame(self.p2_battlefield_frame)
        
        # Update player 1
        self._update_player_display(
            self.p1_info, self.p1_battlefield_frame,
            game_state.player1_state, game_state.turn_player == "player1", 
            game_state.player_to_act == "player1"
        )
        
        # Update player 2
        self._update_player_display(
            self.p2_info, self.p2_battlefield_frame,
            game_state.player2_state, game_state.turn_player == "player2",
            game_state.player_to_act == "player2"
        )
    
    def _clear_frame(self, frame):
        """Clear all widgets from a frame."""
        for widget in frame.winfo_children():
            widget.destroy()
    
    def _update_player_display(self, info_frame, battlefield_frame, 
                              player_state, is_turn_player, is_player_to_act):
        """Update the display for a single player."""
        # Clear existing widgets from info_frame to prevent duplication
        self._clear_frame(info_frame)
        
        # Create life total display (big and on its own line)
        life_frame = ttk.Frame(info_frame)
        life_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 5))
        
        life_text = f"Life: {player_state.life}"
        # Check if this player has priority (is the player to act)
        if is_player_to_act:
            life_text += " (To Act)"
        
        life_label = ttk.Label(life_frame, text=life_text, font=("Arial", 16, "bold"))
        life_label.pack(side=tk.LEFT)
        
        # Create a second frame for other info
        other_info_frame = ttk.Frame(info_frame)
        other_info_frame.pack(side=tk.TOP, fill=tk.X)
        
        # Update other info with card names in hand, graveyard, and exile
        info_text = ""
        if player_state.mana_pool:
            mana_str = ", ".join([f"{color}:{amount}" for color, amount in player_state.mana_pool.items()])
            info_text += f"Mana: {mana_str} | "
        
        # Add card names to hand info (only if hand is not empty)
        if player_state.hand:
            hand_names = [card.name for card in player_state.hand]
            info_text += f"Hand: {', '.join(hand_names)} | "
        
        # Add graveyard card names (only if graveyard is not empty)
        if player_state.graveyard:
            graveyard_names = [card.name for card in player_state.graveyard]
            info_text += f"Graveyard: {', '.join(graveyard_names)} | "
        
        # Add exile card names (only if exile is not empty)
        if player_state.exile:
            exile_names = [card.name for card in player_state.exile]
            info_text += f"Exile: {', '.join(exile_names)} | "
        
        info_text += f"Battlefield: {len(player_state.battlefield)}"
        
        if is_turn_player:
            info_text += " | TURN PLAYER"
        
        other_info_label = ttk.Label(other_info_frame, text=info_text, font=("Arial", 10))
        other_info_label.pack(side=tk.LEFT)
        
        # Display battlefield
        if player_state.battlefield:
            ttk.Label(battlefield_frame, text="Battlefield:", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=(0, 5))
            for permanent in player_state.battlefield:
                self._display_permanent_image(battlefield_frame, permanent, size=(80, 112))
    
    def _display_card_image(self, parent, card: Card, size: Tuple[int, int] = (80, 112), tapped: bool = False, modifiers: str = "", quantity: int = 1):
        """Display a card image in the given parent."""
        try:
            # Get PIL Image from cache or download
            pil_image = self._get_card_image(card, size)
            if pil_image:
                # Create cache key for PhotoImage (including rotation state)
                rotation_suffix = "_tapped" if tapped else "_untapped"
                photo_cache_key = f"{card.name}_{size[0]}x{size[1]}{rotation_suffix}"
                
                # Check if we already have the appropriate PhotoImage cached
                if photo_cache_key in self.photo_image_cache:
                    photo_image = self.photo_image_cache[photo_cache_key]
                else:
                    # Create the appropriate PhotoImage
                    if tapped:
                        # Rotate 30 degrees clockwise for tapped cards
                        rotated_image = pil_image.rotate(-30, expand=True, fillcolor=(35,35,35))
                        photo_image = ImageTk.PhotoImage(rotated_image)
                    else:
                        photo_image = ImageTk.PhotoImage(pil_image)
                    
                    # Cache the PhotoImage
                    self.photo_image_cache[photo_cache_key] = photo_image
                
                # Create a frame to hold both the card image and modifiers text
                card_frame = ttk.Frame(parent)
                card_frame.pack(side=tk.LEFT, padx=2)
                
                label = ttk.Label(card_frame, image=photo_image)
                label.image = photo_image  # Keep a reference
                label.pack(side=tk.TOP)
                
                # Add quantity text if > 1
                if quantity > 1:
                    quantity_label = ttk.Label(card_frame, text=f"x{quantity}", font=("Arial", 10, "bold"), foreground="red")
                    quantity_label.pack(side=tk.TOP)
                
                # Add modifiers text if present
                if modifiers:
                    modifier_label = ttk.Label(card_frame, text=modifiers, font=("Arial", 8), wraplength=80)
                    modifier_label.pack(side=tk.TOP)
                
                # Add tooltip with card name
                tooltip_text = f"{" "*5}{card.name}"
                if quantity > 1:
                    tooltip_text += f" x{quantity}"
                if tapped:
                    tooltip_text += " [Tapped]"
                tooltip_text += f"{" "*5}"
                self._create_tooltip(label, tooltip_text)
        except Exception as e:
            # Fallback to text display
            print(f"Error displaying card image for {card.name}: {e}")
            text = card.name[:10] + "..."
            if tapped:
                text += " [Tapped]"
            if quantity > 1:
                text += f"\nx{quantity}"
            if modifiers:
                text += f"\n{modifiers}"
            label = ttk.Label(parent, text=text, relief=tk.SUNKEN if tapped else tk.RAISED)
            label.pack(side=tk.LEFT, padx=2)
    
    def _display_permanent_image(self, parent, permanent, size: Tuple[int, int] = (80, 112)):
        """Display a permanent image in the given parent."""
        quantity = getattr(permanent, 'quantity', 1)
        
        if permanent.card:
            self._display_card_image(parent, permanent.card, size, tapped=permanent.tapped, modifiers=permanent.modifiers, quantity=quantity)
        else:
            # Token - display as text
            text = permanent.name
            if permanent.is_creature() and permanent.power and permanent.toughness:
                text += f"\n{permanent.power}/{permanent.toughness}"

            if permanent.tapped:
                text += " [Tapped]"
            
            # Add quantity if > 1
            if quantity > 1:
                text += f"\nx{quantity}"
            
            # Create a frame to hold both the token text and modifiers text
            token_frame = ttk.Frame(parent)
            token_frame.pack(side=tk.LEFT, padx=2)
            
            token_label = ttk.Label(token_frame, text=text, relief=tk.SUNKEN if permanent.tapped else tk.RAISED, width=10)
            token_label.pack(side=tk.TOP)
            
            # Add modifiers text if present
            if permanent.modifiers:
                modifier_label = ttk.Label(token_frame, text=permanent.modifiers, font=("Arial", 8), wraplength=80)
                modifier_label.pack(side=tk.TOP)
            
            # Add tooltip
            tooltip_text = f"{" "*5}{permanent.name}"
            if permanent.is_creature() and permanent.power and permanent.toughness:
                tooltip_text += f" ({permanent.power}/{permanent.toughness})"
            if quantity > 1:
                tooltip_text += f" x{quantity}"
            if permanent.tapped:
                tooltip_text += " [Tapped]"
            tooltip_text += f"{" "*5}"
            self._create_tooltip(token_label, tooltip_text)
        
    def _get_card_image(self, card: Card, size: Tuple[int, int]) -> Optional[Image.Image]:
        """Get a card PIL Image, using cache if available."""
        cache_key = f"{card.name}_{size[0]}x{size[1]}"
        
        if cache_key in self.card_images:
            return self.card_images[cache_key]
        
        try:
            # Download image in a separate thread to avoid blocking
            image = self._download_card_image(card.name, size)
            if image:
                self.card_images[cache_key] = image
                return image
        except Exception as e:
            print(f"Error loading card image for {card.name}: {e}")
        
        return None
    
    def _download_card_image(self, card_name: str, size: Tuple[int, int]) -> Optional[Image.Image]:
        """Download a card image from Scryfall and return PIL Image."""
        try:
            # Get card image URL from Scryfall
            api_url = f"https://api.scryfall.com/cards/named?exact={card_name}"
            response = requests.get(api_url, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            image_uris = data.get('image_uris', {})
            image_url = image_uris.get('normal') or image_uris.get('small')
            
            if image_url:
                # Download image
                img_response = requests.get(image_url, timeout=10)
                img_response.raise_for_status()
                
                # Open and resize image
                image = Image.open(io.BytesIO(img_response.content))
                image = image.resize(size, Image.Resampling.LANCZOS)
                
                return image
        except Exception as e:
            print(f"Error downloading card image for {card_name}: {e}")
        
        return None
    
    def _create_tooltip(self, widget, text):
        """Create a tooltip for a widget."""
        def on_enter(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            label = ttk.Label(tooltip, text=text, background="lightyellow", 
                            relief=tk.FLAT, borderwidth=1)
            label.pack()
            widget.tooltip = tooltip
        
        def on_leave(event):
            if hasattr(widget, 'tooltip'):
                widget.tooltip.destroy()
                del widget.tooltip
        
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    def _on_window_close(self):
        """Handle window close event."""
        # Call the callback if provided
        if self.on_close_callback:
            self.on_close_callback()
        
        self.window.destroy()


class VisualDisplayApp:
    """Main application for visual display."""
    
    def __init__(self, game_tree: GameTree, gemini_client: GeminiClient):
        self.game_tree: GameTree = game_tree
        self.gemini_client: GeminiClient = gemini_client
        
        # Create the main tree window (which is now the root)
        self.tree_window = GameTreeWindow(game_tree, self._on_node_selected)
    
    def _on_node_selected(self, node: GameTreeNode, expand: bool = False):
        """Handle node selection from tree window."""
        # Open state window if not already open
        if not self.tree_window.state_window:
            self.tree_window.open_state_window()
        
        # Update state window
        if self.tree_window.state_window:
            self.tree_window.state_window.update_game_tree_node(node)
        
        # Handle expansion request
        if expand and self.gemini_client and not node.is_terminal and len(node.children) == 0:
            # Expand node in a separate thread to avoid blocking UI
            threading.Thread(target=self._expand_node, args=(node,), daemon=True).start()
    
    def _expand_node(self, node: GameTreeNode):
        """Expand a node using the Gemini client."""
        print(f"Expanding node {node.node_id}")
        child_nodes = self.game_tree.expand_node(node, self.gemini_client, max_children=5)
        
        # Update tree window in main thread
        self.tree_window.window.after(0, lambda: self._finish_expansion(node))
        
    def _finish_expansion(self, node: GameTreeNode):
        """Finish expansion by removing from expanding set and refreshing tree."""
        self.tree_window.expanding_nodes.discard(node.node_id)
        self.tree_window.refresh_tree()
    
    def run(self):
        """Run the application."""
        # Start the main loop
        self.tree_window.window.mainloop()

"""Data models for the UI tree."""

from __future__ import annotations
import json
from dataclasses import dataclass, field


@dataclass
class BoundingBox:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center(self) -> tuple[int, int]:
        return ((self.left + self.right) // 2, (self.top + self.bottom) // 2)

    def intersect(self, other: BoundingBox) -> BoundingBox:
        return BoundingBox(
            left=max(self.left, other.left),
            top=max(self.top, other.top),
            right=min(self.right, other.right),
            bottom=min(self.bottom, other.bottom),
        )

    def is_valid(self) -> bool:
        return self.width > 0 and self.height > 0

    def contains_point(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom


@dataclass
class TreeElementNode:
    """An interactive UI element discovered in the tree."""
    name: str
    control_type: str
    bounding_box: BoundingBox
    window_name: str
    metadata: dict = field(default_factory=dict)

    @property
    def center(self) -> tuple[int, int]:
        return self.bounding_box.center


@dataclass
class ScrollElementNode:
    """A scrollable region in the UI tree."""
    name: str
    control_type: str
    bounding_box: BoundingBox
    window_name: str
    metadata: dict = field(default_factory=dict)

    @property
    def center(self) -> tuple[int, int]:
        return self.bounding_box.center


@dataclass
class TreeState:
    """Result of a UI tree extraction."""
    interactive_nodes: list[TreeElementNode] = field(default_factory=list)
    scrollable_nodes: list[ScrollElementNode] = field(default_factory=list)

    def get_node_by_label(self, label: int) -> TreeElementNode | ScrollElementNode | None:
        """Resolve a label to a node. Interactive nodes are 0..N-1, scrollable are N..M-1."""
        if label < len(self.interactive_nodes):
            return self.interactive_nodes[label]
        scroll_idx = label - len(self.interactive_nodes)
        if 0 <= scroll_idx < len(self.scrollable_nodes):
            return self.scrollable_nodes[scroll_idx]
        return None

    def get_coordinates_from_label(self, label: int) -> tuple[int, int]:
        """Resolve a label to (x, y) center coordinates. Raises IndexError if out of range."""
        node = self.get_node_by_label(label)
        if node is None:
            total = len(self.interactive_nodes) + len(self.scrollable_nodes)
            raise IndexError(f"Label {label} out of range (0-{total - 1})")
        return node.center

    def interactive_elements_to_string(self) -> str:
        if not self.interactive_nodes:
            return "No interactive elements found."
        lines = ["# id|window|control_type|name|coords|metadata"]
        for idx, node in enumerate(self.interactive_nodes):
            cx, cy = node.center
            lines.append(
                f"{idx}|{node.window_name}|{node.control_type}|{node.name}|({cx},{cy})|{json.dumps(node.metadata)}"
            )
        return "\n".join(lines)

    def scrollable_elements_to_string(self) -> str:
        if not self.scrollable_nodes:
            return "No scrollable elements found."
        base = len(self.interactive_nodes)
        lines = ["# id|window|control_type|name|coords|metadata"]
        for idx, node in enumerate(self.scrollable_nodes):
            cx, cy = node.center
            lines.append(
                f"{base + idx}|{node.window_name}|{node.control_type}|{node.name}|({cx},{cy})|{json.dumps(node.metadata)}"
            )
        return "\n".join(lines)

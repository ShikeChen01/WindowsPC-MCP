"""Shared test fixtures for WindowsMCP Custom."""

import pytest
from dataclasses import dataclass


@dataclass
class MockBounds:
    """Mock screen bounds for testing without a real virtual display."""
    x: int = 3840
    y: int = 0
    width: int = 1920
    height: int = 1080

    @property
    def left(self) -> int:
        return self.x

    @property
    def top(self) -> int:
        return self.y

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


@pytest.fixture
def agent_bounds():
    """Default agent screen bounds for tests."""
    return MockBounds()


@pytest.fixture
def user_bounds():
    """Default user screen bounds for tests."""
    return MockBounds(x=0, y=0, width=1920, height=1080)

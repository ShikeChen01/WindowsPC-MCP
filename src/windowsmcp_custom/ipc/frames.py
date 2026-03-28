"""Shared memory frame buffer for delivering screenshots to the UI viewer."""
import logging
logger = logging.getLogger(__name__)

class FrameBuffer:
    """Placeholder for frame delivery to the viewer UI."""
    def __init__(self):
        self._latest_frame = None

    def push_frame(self, frame_data: bytes, width: int, height: int):
        self._latest_frame = (frame_data, width, height)

    def get_frame(self):
        return self._latest_frame

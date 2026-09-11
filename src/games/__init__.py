"""Game packages share a quiet appliance-console startup policy."""

import os

# Pygame otherwise writes a two-line support prompt to tty1 during import.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

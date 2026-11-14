"""Agent-to-frontend event-stream lifecycle contract validator. Stdlib only."""
from .validator import RULES, SessionReport, validate_session
from .statepatch import apply_patch

__all__ = ["RULES", "SessionReport", "validate_session", "apply_patch"]

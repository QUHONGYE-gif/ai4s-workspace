"""Standard-library task declaration contract, usable by UI and engine services."""

from .registry import DeclarationError, DeclarationRegistry, validate_declaration

__all__ = ["DeclarationError", "DeclarationRegistry", "validate_declaration"]

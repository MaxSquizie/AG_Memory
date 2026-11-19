"""Independent Russian grammar fragment. Analysis only, without memory side effects."""
from .parser import Probe, Result, analyze

__all__ = ['Probe', 'Result', 'analyze']

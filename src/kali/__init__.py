"""
Kali is a web service framework with some special tweaks specifically aimed
at working well in a single-thread run-time. It's conceived as an alternative
to desktop application development.
"""

from .version import *
from .implementation import *
from . import forms
__all__ = implementation.__all__

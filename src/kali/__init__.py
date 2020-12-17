"""
Kali is a web service framework with some special tweaks specifically aimed
at working well in a single-thread run-time. It's conceived as an alternative
to desktop application development.
"""

from .version import *
from .templates import *
from .requesting import *
from .responding import *
from .implementation import *
from . import forms
__all__ = requesting.__all__ + responding.__all__ + templates.__all__ + implementation.__all__

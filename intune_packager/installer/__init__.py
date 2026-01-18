"""
Installer processing module.
"""

from .detector import InstallerDetector, InstallerType
from .metadata import MetadataExtractor
from .wrapper import IntuneWrapper

__all__ = ["InstallerDetector", "InstallerType", "MetadataExtractor", "IntuneWrapper"]

"""Music Video Organizer public API."""

from mvo.analyzer import LibraryAnalyzer
from mvo.duplicates import DuplicateDetector
from mvo.musicbrainz import MusicBrainzClient
from mvo.parser import FilenameParser
from mvo.planner import FolderPlanner
from mvo.scanner import LibraryScanner

__all__ = [
    "DuplicateDetector",
    "FilenameParser",
    "FolderPlanner",
    "LibraryAnalyzer",
    "LibraryScanner",
    "MusicBrainzClient",
]
__version__ = "0.6.0"

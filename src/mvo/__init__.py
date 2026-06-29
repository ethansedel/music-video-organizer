"""Music Video Organizer public API."""

from mvo.acoustid import AcoustIDClient, FingerprintExtractor
from mvo.analyzer import LibraryAnalyzer
from mvo.coverart import CoverArtClient
from mvo.duplicates import DuplicateDetector
from mvo.musicbrainz import MusicBrainzClient
from mvo.parser import FilenameParser
from mvo.planner import FolderPlanner
from mvo.scanner import LibraryScanner

__all__ = [
    "DuplicateDetector",
    "AcoustIDClient",
    "CoverArtClient",
    "FilenameParser",
    "FolderPlanner",
    "FingerprintExtractor",
    "LibraryAnalyzer",
    "LibraryScanner",
    "MusicBrainzClient",
]
__version__ = "0.8.0.dev0"

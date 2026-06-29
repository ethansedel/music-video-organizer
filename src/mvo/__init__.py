"""Music Video Organizer public API."""

from mvo.acoustid import AcoustIDClient, FingerprintExtractor
from mvo.analyzer import LibraryAnalyzer
from mvo.coverart import CoverArtClient
from mvo.duplicates import DuplicateDetector
from mvo.executor import PlanExecutor
from mvo.musicbrainz import MusicBrainzClient
from mvo.parser import FilenameParser
from mvo.planner import FolderPlanner
from mvo.preflight import PlanPreflight
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
    "PlanExecutor",
    "PlanPreflight",
]
__version__ = "1.0.0.dev0"

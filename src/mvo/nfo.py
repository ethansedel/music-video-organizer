"""Safe Jellyfin-compatible NFO previews and exports."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree

from mvo.models import AnalyzedVideo


class JellyfinNfoWriter:
    """Render and atomically create sidecar metadata without overwriting files."""

    def preview(self, video: AnalyzedVideo) -> tuple[Path, str]:
        """Return the adjacent NFO path and its proposed XML document."""

        parsed = video.parsed
        root = ElementTree.Element("movie")
        display_title = (
            f"{parsed.artist} - {parsed.title}" if parsed.artist else parsed.title
        )
        ElementTree.SubElement(root, "title").text = display_title
        ElementTree.SubElement(root, "originaltitle").text = parsed.title
        if parsed.artist:
            ElementTree.SubElement(root, "studio").text = parsed.artist
        if parsed.year is not None:
            ElementTree.SubElement(root, "year").text = str(parsed.year)
        for artist in parsed.featured_artists:
            ElementTree.SubElement(root, "tag").text = f"Featuring: {artist}"
        for version in parsed.versions:
            ElementTree.SubElement(root, "tag").text = version
        ElementTree.SubElement(root, "tag").text = "Music Video"
        ElementTree.indent(root, space="  ")
        content = ElementTree.tostring(root, encoding="unicode", xml_declaration=False)
        document = f'<?xml version="1.0" encoding="UTF-8"?>\n{content}\n'
        return video.source.path.with_suffix(".nfo"), document

    def write(self, video: AnalyzedVideo) -> Path:
        """Create one NFO sidecar atomically and refuse to replace an existing one."""

        destination, content = self.preview(video)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"NFO already exists: {destination.name}")
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            os.link(temporary, destination, follow_symlinks=False)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return destination

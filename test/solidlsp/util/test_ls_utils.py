from __future__ import annotations

import hashlib
import os
import stat
import zipfile
from pathlib import Path
from unittest.mock import patch

from solidlsp.ls_utils import FileUtils


class _FakeResponse:
    def __init__(self, payload: bytes, final_url: str) -> None:
        self.status_code = 200
        self.headers = {"content-encoding": "gzip"}
        self.url = final_url
        self._payload = payload

    def iter_content(self, chunk_size: int = 1):
        for offset in range(0, len(self._payload), chunk_size):
            yield self._payload[offset : offset + chunk_size]

    def close(self) -> None:
        return None


def test_download_file_verified_writes_decoded_response_body(tmp_path: Path) -> None:
    """Gzip-encoded transfer bodies should be written as decoded payload bytes."""
    payload = b"PK\x03\x04zip-content"
    target_path = tmp_path / "downloaded.vsix"
    final_url = "https://marketplace.visualstudio.com/example.vsix"

    with patch(
        "solidlsp.ls_utils.requests.get",
        return_value=_FakeResponse(payload, final_url),
    ):
        FileUtils.download_file_verified(
            "https://marketplace.visualstudio.com/example.vsix",
            str(target_path),
            expected_sha256=hashlib.sha256(payload).hexdigest(),
            allowed_hosts=("marketplace.visualstudio.com",),
        )

    assert target_path.read_bytes() == payload


def test_extract_zip_archive_overwrites_readonly_file(tmp_path: Path) -> None:
    """Re-extracting a zip into a directory that already contains a read-only copy of the same
    file (e.g. plugin jars from a prior vscode-java install where the zip stored 0o444 mode bits)
    must succeed. Without unlinking first, ``open(..., "wb")`` fails with EACCES.
    """
    archive_path = tmp_path / "bundle.zip"
    target_dir = tmp_path / "out"
    target_dir.mkdir()

    # Build a zip that stores the file with read-only Unix permissions, mirroring how
    # vscode-java ships some of its server plugin jars (e.g. slf4j.api_*.jar).
    info = zipfile.ZipInfo("plugin.jar")
    info.create_system = 3  # ZIP_SYSTEM_UNIX
    info.external_attr = (0o444 & 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, b"new contents")

    # Pre-populate the target with a read-only file at the same relative path,
    # simulating a stale install left over from an older bundle version.
    stale_file = target_dir / "plugin.jar"
    stale_file.write_bytes(b"old contents")
    os.chmod(stale_file, stat.S_IREAD)

    FileUtils._extract_zip_archive(str(archive_path), str(target_dir))

    assert stale_file.read_bytes() == b"new contents"

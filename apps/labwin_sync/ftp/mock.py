"""
Mock FTP connector for development and testing.

Provides in-memory PDF files that simulate the FTP server.
Filenames follow the pattern {NUMERO_FLD}.pdf to match Study.sample_id.
"""

import logging

from .base import LabWinFTPConnector

logger = logging.getLogger(__name__)

# Minimal valid PDF content for testing
MOCK_PDF_CONTENT = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
    b"0000000058 00000 n \n0000000115 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
)

# Sample FTP files matching mock DETERS NUMERO_FLDs
MOCK_FTP_FILES = {
    "100001.pdf": MOCK_PDF_CONTENT,
    "100002.pdf": MOCK_PDF_CONTENT,
    "100003.pdf": MOCK_PDF_CONTENT,
}


class MockFTPConnector(LabWinFTPConnector):
    """Mock FTP connector returning in-memory PDF files for dev/testing."""

    def __init__(self, files=None):
        self._connected = False
        self._files = dict(files) if files else dict(MOCK_FTP_FILES)
        self._deleted = set()

    def connect(self):
        self._connected = True
        logger.info("MockFTPConnector connected (using in-memory PDF files)")

    def disconnect(self):
        self._connected = False
        logger.info("MockFTPConnector disconnected")

    def list_pdf_files(self):
        return [f for f in self._files if f not in self._deleted]

    def download_file(self, filename):
        if filename in self._deleted:
            raise FileNotFoundError(f"File {filename} has been deleted")
        content = self._files.get(filename)
        if content is None:
            raise FileNotFoundError(f"File {filename} not found on FTP server")
        return content

    def delete_file(self, filename):
        if filename not in self._files or filename in self._deleted:
            raise FileNotFoundError(f"File {filename} not found on FTP server")
        self._deleted.add(filename)
        logger.info("MockFTPConnector deleted file: %s", filename)

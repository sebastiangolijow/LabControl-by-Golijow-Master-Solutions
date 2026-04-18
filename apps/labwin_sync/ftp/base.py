"""
Abstract base class defining the FTP connector interface for PDF fetching.

All FTP connectors (real FTP, mock) must implement this interface.
"""

from abc import ABC, abstractmethod


class LabWinFTPConnector(ABC):
    """Interface for connecting to an FTP server to fetch PDF result files."""

    @abstractmethod
    def connect(self):
        """Establish connection to the FTP server."""

    @abstractmethod
    def disconnect(self):
        """Close the connection to the FTP server."""

    @abstractmethod
    def list_pdf_files(self):
        """List all PDF files available on the FTP server.

        Returns:
            List of filenames (str), e.g. ["100001.pdf", "100002.pdf"]
        """

    @abstractmethod
    def download_file(self, filename):
        """Download a PDF file from the FTP server.

        Args:
            filename: Name of the file to download (e.g. "100001.pdf")

        Returns:
            bytes: The file content.
        """

    @abstractmethod
    def delete_file(self, filename):
        """Delete a file from the FTP server after successful processing.

        Args:
            filename: Name of the file to delete.
        """

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False

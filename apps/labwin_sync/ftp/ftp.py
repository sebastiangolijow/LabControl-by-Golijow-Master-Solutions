"""
Real FTP connector for connecting to the LabWin FTP server.

Uses Python's ftplib to connect and download PDF result files.
"""

import logging
from ftplib import FTP, FTP_TLS
from io import BytesIO

from django.conf import settings

from .base import LabWinFTPConnector

logger = logging.getLogger(__name__)


class FTPConnector(LabWinFTPConnector):
    """Real FTP connector for the LabWin results server."""

    def __init__(self):
        self._ftp = None

    def connect(self):
        host = settings.LABWIN_FTP_HOST
        port = settings.LABWIN_FTP_PORT
        user = settings.LABWIN_FTP_USER
        password = settings.LABWIN_FTP_PASSWORD
        use_tls = getattr(settings, "LABWIN_FTP_USE_TLS", False)
        directory = getattr(settings, "LABWIN_FTP_DIRECTORY", "/results")

        logger.info("Connecting to FTP server %s:%d", host, port)

        if use_tls:
            self._ftp = FTP_TLS()
        else:
            self._ftp = FTP()

        self._ftp.connect(host, port)
        self._ftp.login(user, password)

        if use_tls:
            self._ftp.prot_p()

        if directory:
            self._ftp.cwd(directory)

        logger.info("FTP connected, working directory: %s", self._ftp.pwd())

    def disconnect(self):
        if self._ftp:
            try:
                self._ftp.quit()
            except Exception:
                self._ftp.close()
            self._ftp = None
            logger.info("FTP disconnected")

    def list_pdf_files(self):
        files = self._ftp.nlst()
        return [f for f in files if f.lower().endswith(".pdf")]

    def download_file(self, filename):
        buffer = BytesIO()
        self._ftp.retrbinary(f"RETR {filename}", buffer.write)
        return buffer.getvalue()

    def delete_file(self, filename):
        self._ftp.delete(filename)
        logger.info("FTP deleted file: %s", filename)

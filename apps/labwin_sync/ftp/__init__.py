"""
LabWin FTP connector factory.

Returns the appropriate FTP connector based on Django settings.
"""

from .base import LabWinFTPConnector  # noqa: F401


def get_ftp_connector(use_mock=None):
    """Return the appropriate FTP connector.

    Args:
        use_mock: Override the LABWIN_FTP_USE_MOCK setting. If None, uses the setting.

    Returns:
        A LabWinFTPConnector instance (mock or real FTP).
    """
    from django.conf import settings

    if use_mock is None:
        use_mock = getattr(settings, "LABWIN_FTP_USE_MOCK", True)

    if use_mock:
        from .mock import MockFTPConnector

        return MockFTPConnector()

    from .ftp import FTPConnector

    return FTPConnector()

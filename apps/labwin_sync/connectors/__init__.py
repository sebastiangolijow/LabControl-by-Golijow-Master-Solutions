"""
LabWin database connector factory.

Returns the appropriate connector based on Django settings.
"""

from .base import LabWinConnector  # noqa: F401


def get_connector(use_mock=None):
    """Return the appropriate LabWin connector.

    Args:
        use_mock: Override the LABWIN_USE_MOCK setting. If None, uses the setting.

    Returns:
        A LabWinConnector instance (mock or real Firebird).
    """
    from django.conf import settings

    if use_mock is None:
        use_mock = getattr(settings, "LABWIN_USE_MOCK", True)

    if use_mock:
        from .mock import MockLabWinConnector

        return MockLabWinConnector()

    from .firebird import FirebirdLabWinConnector

    return FirebirdLabWinConnector()

"""
Lightweight logging helpers shared across apps.

We keep this in apps.core so any task can `from apps.core.logging_utils
import ...` without dragging in heavyweight deps. Specifically, the memory
helper falls back to stdlib `resource` when `psutil` isn't installed
(production currently has no psutil — see requirements/base.txt).

Intended usage at the entry/exit of long-running Celery tasks so a future
debugger can see whether a failed sync was OOM-related:

    logger.info("sync_labwin started: %s", memory_summary())
    ...
    logger.info("sync_labwin finished: %s", memory_summary())
"""

import platform
import resource


def current_rss_mb() -> float:
    """Return current process RSS (resident set size) in megabytes.

    Uses `resource.getrusage(RUSAGE_SELF).ru_maxrss`, which the kernel
    reports in:
        - kilobytes on Linux (so we divide by 1024 → MB)
        - bytes on macOS (so we divide by 1024**2 → MB)

    Returns 0.0 if the platform doesn't support rusage (shouldn't happen
    on the Linux containers we deploy to, but tests on macOS still get a
    sensible number).
    """
    try:
        ru_maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (OSError, ValueError):
        return 0.0

    if platform.system() == "Darwin":
        # macOS reports bytes
        return ru_maxrss / (1024 * 1024)
    # Linux (and most Unixen) report kilobytes
    return ru_maxrss / 1024


def memory_summary() -> str:
    """Compact one-liner suitable for embedding in a logger.info() call.

    Example output: "memory: rss=143.2 MB"
    """
    return f"memory: rss={current_rss_mb():.1f} MB"

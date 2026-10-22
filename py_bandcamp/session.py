"""Module-global HTTP session plus a lazy proxy used by submodules.

``SESSION`` is the live default session, built on first access via
:func:`py_bandcamp.transport.default_session`. ``set_session`` swaps it
out wholesale so every call site (including ones that bound the proxy
at import time) starts using the new session immediately.
"""
from py_bandcamp.transport import default_session

SESSION = default_session()


def set_session(session):
    """Replace the global HTTP session (e.g. to inject auth headers,
    a cache, or a mock). Affects every submodule that goes through the
    :data:`HTTP` proxy."""
    global SESSION
    SESSION = session


def get_session():
    """Return the current global session."""
    return SESSION


class _HTTPProxy:
    """Attribute-forwarding proxy to the *current* :data:`SESSION`.

    Submodules import this once and call ``HTTP.get(...)``; the lookup
    resolves to whatever session is live at call time, so
    :func:`set_session` works retroactively (a plain
    ``from session import SESSION as requests`` rebinds the original
    object and would silently keep using the old session).
    """

    def __getattr__(self, name):
        return getattr(SESSION, name)


HTTP = _HTTPProxy()

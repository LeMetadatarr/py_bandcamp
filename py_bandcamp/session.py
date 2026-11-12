"""Module-global HTTP session plus a lazy proxy used by submodules.

``SESSION`` is the live default session, built on first access via
:func:`py_bandcamp.transport.default_session`. ``set_session`` swaps it
out wholesale so every call site (including ones that bound the proxy
at import time) starts using the new session immediately.

Every request made through the proxy, or through a per-instance session
wrapped by :class:`TimedHTTP`, carries a timeout unless the caller sets one.
"""
from py_bandcamp.transport import default_session

SESSION = default_session()

#: Seconds before a request without an explicit ``timeout`` is abandoned.
DEFAULT_TIMEOUT = 30

_TIMED_METHODS = frozenset({"get", "post", "head", "put", "patch", "delete", "options", "request"})

#: Index of the ``timeout`` parameter among the positional arguments of ``Session.request``.
_TIMEOUT_POSITION = {"request": 8}


def set_session(session):
    """Replace the global HTTP session (e.g. to inject auth headers,
    a cache, or a mock). Affects every submodule that goes through the
    :data:`HTTP` proxy."""
    global SESSION
    SESSION = session


def get_session():
    """Return the current global session."""
    return SESSION


class TimedHTTP:
    """Attribute-forwarding proxy to a session that adds a default timeout.

    With no session given it forwards to the *current* :data:`SESSION`, so
    :func:`set_session` works retroactively (a plain
    ``from session import SESSION as requests`` rebinds the original
    object and would silently keep using the old session).
    """

    def __init__(self, session=None):
        self._session = session

    def __getattr__(self, name):
        if name == "_session" or (name.startswith("__") and name.endswith("__")):
            raise AttributeError(name)
        target = self._session if self._session is not None else SESSION
        attr = getattr(target, name)
        if name not in _TIMED_METHODS:
            return attr
        own = getattr(target, "timeout", None)
        if isinstance(own, (int, float, tuple)) and not isinstance(own, bool):
            return attr
        positional = _TIMEOUT_POSITION.get(name)

        def call(*args, **kwargs):
            if positional is None or len(args) <= positional:
                kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
            return attr(*args, **kwargs)

        return call


HTTP = TimedHTTP()

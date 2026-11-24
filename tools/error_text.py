"""One error line for the command line tools.

``str(OSError)`` appends ``repr(filename)``, so a path comes back with every backslash doubled:
``[Errno 13] Permission denied: 'C:\\\\port\\\\mount\\\\blocked'``. That is why ``test_bink_names``,
``test_opus_tags`` and ``test_world_names`` cannot find the folder they blocked on a Windows host, while the
same assertion holds on POSIX. A message that names a path should print the path as it is -- the rule
``bvh_index`` already applies at its own call sites (``{error.filename or root}: skipped (...)``, and
``test_bvh_index`` forbids ``[Errno`` in the output).

``describe`` returns ``<path>: <reason>`` for an :class:`OSError` that carries a file name and ``str(error)``
for every other exception, so a caller never prints ``[Errno ...]`` or a quoted path.
"""
from __future__ import annotations

import os


def describe(error: BaseException) -> str:
    """The text of a CLI error line; a file name is printed as it is, without ``repr`` quoting."""
    if not isinstance(error, OSError) or not error.filename:
        return str(error)
    filename = error.filename
    if isinstance(filename, bytes):
        filename = os.fsdecode(filename)
    elif not isinstance(filename, str):
        return str(error)
    return f"{filename}: {error.strerror or str(error)}"

"""`ece` entrypoint.

stdout is forced to UTF-8 before Typer is imported.  On Windows the console
codepage is cp1252, and the report writers use characters (`→`, `·`, box rules)
that cp1252 cannot encode — `ece optimize` died with a UnicodeEncodeError on the
very platform the demo runs on.  Reconfiguring here fixes every command at once,
rather than sanitising each string at the call site.
"""

import sys

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):   # not a TextIOWrapper (piped/captured)
        pass

from app.main_cli import app

if __name__ == "__main__":
    app()

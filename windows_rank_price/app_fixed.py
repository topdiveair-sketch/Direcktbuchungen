from __future__ import annotations

"""Stable Windows launcher for Zuhause am Bach - Rang & Preis.

The base desktop app already performs network requests on a worker thread and
hands results back to Tk through a Queue.  Keep a single result consumer here;
previously this launcher added a second queue consumer with a different event
name ("result" vs. "ok"), causing valid API payloads to be rendered as error
text in the Google rank card.
"""

from app import App


if __name__ == "__main__":
    App().mainloop()

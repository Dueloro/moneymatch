"""Pytest bootstrap.

The serverless modules import their siblings as ``_lib.<module>`` (see
``api/index.py``, which inserts ``api/`` onto ``sys.path`` at runtime). Mirror
that here so tests can ``from _lib import tournament`` exactly like production.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "api"))

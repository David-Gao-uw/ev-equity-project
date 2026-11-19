"""Make the modules in ``src/`` importable from every test file.

``src`` is put first on the path so that ``import data`` finds
``src/data.py`` rather than the ``data/`` directory of raw CSVs.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

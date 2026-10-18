#!/usr/bin/env python3
"""Start the demo frontend and API; requires Python 3.10+ and no extra packages."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from workbench.server import main

if __name__ == '__main__':
    main()

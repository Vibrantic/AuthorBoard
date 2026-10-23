import os
import sys
import traceback

# Project root (one level up from tools/) onto sys.path so `import main` works.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _hook(t, v, tb):
    traceback.print_exception(t, v, tb)
    sys.__excepthook__(t, v, tb)


sys.excepthook = _hook

import main
main.main()
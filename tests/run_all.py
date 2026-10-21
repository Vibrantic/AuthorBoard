# SPDX-License-Identifier: GPL-3.0-or-later
"""Run every test script in its own process and print a summary.

    python tests/run_all.py

Each script is a plain Python program that raises an AssertionError on failure
and prints ``ALL OK`` (or ends normally) on success.  Qt runs headless.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = [
    ("test_inspector_stability.py", []),
    ("test_rich_text.py", []),
    ("test_canvas.py", []),
    ("test_integration.py", []),
    ("test_shelf_library.py", []),
    ("test_shelf_timeline.py", []),
    ("test_i18n.py", []),
    ("test_showcase.py", ["de"]),
    ("test_showcase.py", ["en"]),
]


def main():
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    failed = []
    for name, args in SCRIPTS:
        proc = subprocess.run([sys.executable, os.path.join(HERE, name), *args],
                              capture_output=True, text=True, env=env)
        ok = proc.returncode == 0
        print(f"{'PASS' if ok else 'FAIL'}  {name} {' '.join(args)}")
        if not ok:
            failed.append(name)
            print(proc.stdout[-1500:], proc.stderr[-2500:])
    print(f"\n{len(SCRIPTS) - len(failed)}/{len(SCRIPTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

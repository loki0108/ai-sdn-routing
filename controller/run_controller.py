"""
Start OS-Ken controller apps.

Recent OS-Ken versions no longer ship the `osken-manager` command,
so this small script does its job.

Usage (from the project root, with the venv active):
    python -m controller.run_controller <app module> [<app module> ...]
"""

import logging
import os
import signal
import sys

# Must run before anything else touches networking:
# lets one program handle many switch connections at once.
from os_ken.lib import hub
hub.patch(thread=False)

from os_ken import cfg                           # noqa: E402
from os_ken.base.app_manager import AppManager   # noqa: E402

def stop_controller(signum, frame):
    """Exit cleanly on Ctrl+C (OS-Ken's own shutdown code crashes in this version)."""
    print("\n*** Controller stopped")
    os._exit(0)

def main():
    apps = sys.argv[1:]
    if not apps:
        print("Usage: python -m controller.run_controller <app module> [...]")
        sys.exit(1)

    # Show the controller's log messages in the terminal
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    # Load OS-Ken's default settings (e.g. listen on port 6653)
    cfg.CONF(args=[], project="os_ken")

    print(f"*** Starting OS-Ken with apps: {', '.join(apps)}")
    print("*** Press Ctrl+C to stop")
    signal.signal(signal.SIGINT, stop_controller)
    AppManager.run_apps(apps)   # blocks here until stopped


if __name__ == "__main__":
    main()
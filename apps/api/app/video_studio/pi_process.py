"""Private transport to the long-lived native Toonflow host; no Agent loop."""
from .native_host import run_native


def run_process(config: dict, callback, check_cancel, progress=None, poll_controls=None) -> dict:
    return run_native(config, callback, check_cancel, progress, poll_controls)

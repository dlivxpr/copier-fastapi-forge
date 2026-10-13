from __future__ import annotations

import os
import signal
import subprocess


def stop_process_group(process: subprocess.Popen[str]) -> tuple[str, bool]:
    """Stop a spawned process tree, forcing termination only after a grace period."""
    if os.name == "nt":
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        os.killpg(process.pid, signal.SIGINT)
    forced = False
    try:
        stdout, _ = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        forced = True
        if os.name == "nt":
            killed = subprocess.run(
                ("taskkill", "/PID", str(process.pid), "/T", "/F"),
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert killed.returncode == 0, killed.stderr
        else:
            os.killpg(process.pid, signal.SIGKILL)
        stdout, _ = process.communicate(timeout=30)
    return stdout, forced

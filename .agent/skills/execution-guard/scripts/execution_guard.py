import os
import sys
import signal
import subprocess
import time
import functools
from contextlib import contextmanager

class TimeoutException(Exception):
    """Raised when a guarded section of code exceeds its timeout."""
    pass

def _timeout_handler(signum, frame):
    raise TimeoutException("Timed out!")

@contextmanager
def ScriptGuardian(seconds):
    """
    Context manager that enforces a hard timeout on a block of code.
    Uses SIGALRM (Linux only).
    """
    if os.name == 'nt' or seconds <= 0:
        # On Windows or for 0 timeout, we just yield (no-op)
        yield
        return

    # Set the signal handler and a 5-second alarm
    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        # Disable the alarm
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

def timeout_guard(seconds):
    """
    Decorator version of ScriptGuardian.
    Usage:
        @timeout_guard(60)
        def long_running_function():
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with ScriptGuardian(seconds):
                return func(*args, **kwargs)
        return wrapper
    return decorator

def safe_run_subprocess(command, timeout=30, label="Process", cwd=None, env=None):
    """
    Hardened wrapper for subprocess.Popen that ensures process and children 
    are killed on timeout.
    """
    start_time = time.time()
    
    # On Linux, start in a new process group so we can kill the whole group
    preexec = os.setpgrp if os.name != 'nt' else None
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0

    try:
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=cwd or os.getcwd(),
            env=env or os.environ,
            preexec_fn=preexec,
            creationflags=creationflags
        )
        
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            return {
                "success": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "duration": time.time() - start_time
            }
        except subprocess.TimeoutExpired:
            # Kill the process group
            if os.name != 'nt':
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
            
            return {
                "success": False,
                "error": "TIMEOUT",
                "message": f"{label} killed after {timeout}s",
                "duration": time.time() - start_time
            }
    except Exception as e:
        return {
            "success": False,
            "error": "EXCEPTION",
            "message": f"{label} failed: {str(e)}",
            "duration": time.time() - start_time
        }

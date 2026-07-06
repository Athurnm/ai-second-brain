#!/usr/bin/env python3
"""
Execute a command and capture output to a file (hardened version).

Usage:
  python exec_and_capture.py output_file --timeout 30 -- python some_script.py arg1

Key features:
- Uses Popen with explicit kill on timeout (no zombie processes)
- Forces UTF-8 encoding in subprocess via PYTHONIOENCODING
- Writes partial output even if the command times out
- Non-zero exit codes: 124 = timeout, others = command exit code
"""
import subprocess
import sys
import os
import argparse
import time

def main():
    parser = argparse.ArgumentParser(description="Execute command and capture output to file")
    parser.add_argument("output_file", help="File to write output to")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds (default: 60)")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute (use -- before command)")

    args = parser.parse_args()

    command = args.command
    if command and command[0] == '--':
        command = command[1:]

    if not command:
        print("Error: No command specified", flush=True)
        sys.exit(1)

    print(f"Executing: {' '.join(command)} (timeout={args.timeout}s)", flush=True)
    start = time.time()

    try:
        with open(args.output_file, 'w', encoding='utf-8') as f:
            proc = subprocess.Popen(
                command,
                stdout=f,
                stderr=subprocess.STDOUT,
                text=True,
                env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
            )

            try:
                proc.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                # Kill the process forcefully
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=3)
                except Exception:
                    pass

                elapsed = time.time() - start
                # Append timeout notice to the output file
                f.write(f"\n[TIMEOUT] Command killed after {elapsed:.0f}s\n")
                f.flush()
                print(f"Command timed out after {elapsed:.0f}s - process killed", flush=True)
                sys.exit(124)

        elapsed = time.time() - start
        if proc.returncode != 0:
            print(f"Command failed with exit code {proc.returncode} ({elapsed:.1f}s)", flush=True)
            sys.exit(proc.returncode)

        print(f"Done ({elapsed:.1f}s). Output: {args.output_file}", flush=True)

    except FileNotFoundError:
        print(f"Error: Command not found: {command[0]}", flush=True)
        with open(args.output_file, 'w', encoding='utf-8') as f:
            f.write(f"[ERROR] Command not found: {command[0]}\n")
        sys.exit(127)
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()

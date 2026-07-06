import sys
import subprocess
import os
import json

def is_json(line):
    try:
        stripped = line.strip()
        if not stripped.startswith(b'{'):
            return False
        data = json.loads(stripped)
        # MCP messages always have either 'jsonrpc' or they are not MCP
        return "jsonrpc" in data
    except:
        return False

def main():
    # Environment variables are inherited from the parent process
    cmd = ["npx", "-y", "@phuc-nt/mcp-atlassian-server"]
    
    # Run the actual server
    process = subprocess.Popen(
        cmd,
        stdin=sys.stdin,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        bufsize=0  # Unbuffered for real-time communication
    )
    
    try:
        while True:
            line = process.stdout.readline()
            if not line:
                break
            
            if is_json(line):
                # Valid MCP JSON-RPC message, send to stdout
                sys.stdout.buffer.write(line)
                sys.stdout.buffer.flush()
            else:
                # Log message or other noise, redirect to stderr
                sys.stderr.buffer.write(line)
                sys.stderr.buffer.flush()
                
    except KeyboardInterrupt:
        process.terminate()
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait()

if __name__ == "__main__":
    main()

import os
import sys
import argparse
import glob
import time
from datetime import datetime, timedelta
import fnmatch
import platform

def assert_drive_result(result, operation, id_keys=('id', 'documentId', 'fileId', 'spreadsheetId')):
    """
    Shared Drive Operation Verification (CLAUDE.md rule): confirm a Drive/Docs
    write actually produced a file or document identifier before the caller
    reports success. Call this right before printing the success line, in
    place of exiting 0 on an unchecked API response.

    `result` accepts three shapes so every writer can pass whatever it
    already has on hand:
      - a dict/API response, checked for any key in `id_keys`
      - a plain id (string/int) the caller already knows is correct
      - a falsy value (None, {}, '', 0, False), always treated as failure

    On success returns the id that was found (or the passed-through value).
    On failure prints a clear message to stderr and exits nonzero. This is
    the single source of truth for the check; it never returns on failure,
    so callers do not need to branch on the return value unless they want
    the id for logging.
    """
    found = None
    if isinstance(result, dict):
        for key in id_keys:
            val = result.get(key)
            if val:
                found = val
                break
    elif result:
        found = result

    if not found:
        print(
            f"[ERROR] Drive Operation Verification failed for '{operation}': "
            "no file/document ID in the result. Treat this as a FAILURE, not "
            "a success. Verify with a search before assuming the write "
            "happened.",
            file=sys.stderr,
        )
        sys.exit(1)
    return found

def get_creation_time(path):
    """
    Try to get the creation time. 
    On Windows, os.path.getctime is creation time.
    On Unix/Mac, os.stat().st_birthtime is birth time (if available), 
    otherwise st_ctime is metadata change time (not creation).
    """
    if platform.system() == 'Windows':
        return os.path.getctime(path)
    else:
        stat = os.stat(path)
        try:
            return stat.st_birthtime
        except AttributeError:
            # Fallback for Linux/Unix where birthtime isn't standard
            # We return modification time as a fallback if creation isn't available
            return stat.st_mtime

def is_excluded(path, exclude_dirs):
    for exclude in exclude_dirs:
        if exclude in path.split(os.sep):
            return True
    return False

def find_recent(base_dir, hours, mode='modified', exclude_dirs=None, limit=None):
    if exclude_dirs is None:
        exclude_dirs = ['.git', '.DS_Store', 'node_modules']
    
    matches = []
    cutoff_time = time.time() - (hours * 3600)
    
    for root, dirs, files in os.walk(base_dir):
        # Modify dirs in-place to skip excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for file in files:
            if file in exclude_dirs:
                continue
                
            full_path = os.path.join(root, file)
            try:
                if mode == 'modified':
                    file_time = os.path.getmtime(full_path)
                elif mode == 'created':
                    file_time = get_creation_time(full_path)
                else:
                    continue
                
                if file_time > cutoff_time:
                    matches.append((full_path, file_time))
            except OSError:
                continue

    # Sort by time descending (newest first)
    matches.sort(key=lambda x: x[1], reverse=True)
    
    if limit:
        matches = matches[:limit]
        
    for path, timestamp in matches:
        dt = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{dt}] {path}")

def find_by_pattern(base_dir, patterns, exclude_dirs=None, limit=None):
    if exclude_dirs is None:
        exclude_dirs = ['.git', '.DS_Store', 'node_modules']
    
    matches = []
    
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for file in files:
            for pattern in patterns:
                if fnmatch.fnmatch(file, pattern):
                    matches.append(os.path.join(root, file))
                    break # Matched one pattern, move to next file
    
    if limit:
        matches = matches[:limit]
        
    for path in matches:
        print(path)

def main():
    parser = argparse.ArgumentParser(description="Cross-platform file utility.")
    parser.add_argument("--action", choices=['recent_modified', 'recent_created', 'find'], required=True, help="Action to perform")
    parser.add_argument("--dir", required=True, help="Base directory to search")
    parser.add_argument("--hours", type=int, default=24, help="Hours lookback for recent actions")
    parser.add_argument("--patterns", nargs='*', help="File patterns to match (e.g. *.md)")
    parser.add_argument("--exclude", nargs='*', default=['.git', '.DS_Store', 'node_modules'], help="Directories to exclude")
    parser.add_argument("--limit", type=int, default=50, help="Max results to return")

    args = parser.parse_args()

    if args.action == 'recent_modified':
        find_recent(args.dir, args.hours, mode='modified', exclude_dirs=args.exclude, limit=args.limit)
    elif args.action == 'recent_created':
        find_recent(args.dir, args.hours, mode='created', exclude_dirs=args.exclude, limit=args.limit)
    elif args.action == 'find':
        if not args.patterns:
            print("Error: --patterns required for find action")
            return
        find_by_pattern(args.dir, args.patterns, exclude_dirs=args.exclude, limit=args.limit)

if __name__ == "__main__":
    main()

# Server Startup Documentation Fix

## Issue
The FunkyGibbon server must be run from the project root directory, not from within the funkygibbon subdirectory.

## Correct Usage

```bash
# WRONG - This will fail
cd funkygibbon
python -m funkygibbon
# Error: No module named funkygibbon

# CORRECT - Run from project root
cd /workspaces/the-goodies
python -m funkygibbon
# Server starts successfully
```

## Why This Happens
Python's module system requires running the module from a directory where Python can find the package. When you're inside the funkygibbon directory, Python can't find the funkygibbon package because it's looking for funkygibbon/funkygibbon.

## Updated Instructions

1. **Populate the database** (from funkygibbon directory):
   ```bash
   cd funkygibbon
   python populate_db.py
   ```

2. **Start the server** (from project root):
   ```bash
   cd ..  # Go back to project root
   python -m funkygibbon
   ```

## Files Updated
- funkygibbon/README.md
- funkygibbon/HUMAN_TESTING.md
- funkygibbon/populate_db.py
- README.md (project root)

All documentation now correctly shows that the server must be run from the project root directory.

## Database Location Consideration

The SQLite database uses a relative path (`./funkygibbon.db`), which means:
- Database is created in the current working directory
- populate_db.py and the server may use different database files if run from different directories

**Best Practice**: Run both scripts from project root:
```bash
cd /workspaces/the-goodies
python funkygibbon/populate_db.py  # Creates DB here
python -m funkygibbon              # Uses same DB
```
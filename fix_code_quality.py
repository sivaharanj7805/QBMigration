#!/usr/bin/env python3
"""
Code Quality Fixer Script
Fixes all remaining issues for 100/100 code quality:
1. Convert print() to logger calls
2. Replace datetime.utcnow() with datetime.now(timezone.utc)
3. Add missing imports
"""

import os
import re
import sys
from pathlib import Path

# Directories to process
DIRS_TO_PROCESS = [
    'QBMigrationServer',
    'QBMigrationService',
]

# Files to skip (test files, etc.)
SKIP_PATTERNS = [
    'test_',
    '_test.py',
    '__pycache__',
    '.venv',
    'node_modules',
    'fix_code_quality.py',
]

def should_skip(filepath):
    """Check if file should be skipped"""
    for pattern in SKIP_PATTERNS:
        if pattern in filepath:
            return True
    return False

def fix_print_statements(content, filepath):
    """Convert print() to logger.info() and ensure logger import exists"""

    # Skip if no print statements
    if 'print(' not in content:
        return content, False

    modified = False
    lines = content.split('\n')
    new_lines = []
    has_logger = 'logger = ' in content or 'logger=' in content
    has_logging_import = 'import logging' in content

    for i, line in enumerate(lines):
        # Skip comments
        stripped = line.strip()
        if stripped.startswith('#'):
            new_lines.append(line)
            continue

        # Convert print() to logger.info()
        # Handle multi-line prints carefully
        if 'print(' in line and not 'blueprint' in line.lower():
            # Get indentation
            indent = len(line) - len(line.lstrip())
            indent_str = line[:indent]

            # Simple replacement for single-line prints
            if line.count('print(') == 1 and line.rstrip().endswith(')'):
                # Extract the print content
                match = re.search(r'print\((.*)\)$', line.rstrip())
                if match:
                    content_str = match.group(1)
                    # Convert f-strings and regular strings
                    new_line = f'{indent_str}logger.info({content_str})'
                    new_lines.append(new_line)
                    modified = True
                    continue

        new_lines.append(line)

    if modified:
        content = '\n'.join(new_lines)

        # Add logger if not present
        if not has_logger and modified:
            # Find the right place to add logger (after imports)
            lines = content.split('\n')
            insert_idx = 0
            for i, line in enumerate(lines):
                if line.startswith('import ') or line.startswith('from '):
                    insert_idx = i + 1
                elif line.strip() and not line.startswith('#') and not line.startswith('"""') and insert_idx > 0:
                    break

            # Add logging import if needed
            if not has_logging_import:
                lines.insert(insert_idx, 'import logging')
                insert_idx += 1

            # Add logger creation
            lines.insert(insert_idx, '')
            lines.insert(insert_idx + 1, 'logger = logging.getLogger(__name__)')
            lines.insert(insert_idx + 2, '')

            content = '\n'.join(lines)

    return content, modified

def fix_datetime_utcnow(content, filepath):
    """Replace datetime.utcnow() with datetime.now(timezone.utc)"""

    if 'datetime.utcnow()' not in content and 'utcnow()' not in content:
        return content, False

    modified = False

    # Check if timezone is already imported
    has_timezone_import = 'from datetime import' in content and 'timezone' in content

    # Replace datetime.utcnow() with datetime.now(timezone.utc)
    if 'datetime.utcnow()' in content:
        content = content.replace('datetime.utcnow()', 'datetime.now(timezone.utc)')
        modified = True

    # Replace standalone utcnow() calls
    if '.utcnow()' in content:
        content = re.sub(r'(\w+)\.utcnow\(\)', r'\1.now(timezone.utc)', content)
        modified = True

    # Add timezone import if needed
    if modified and not has_timezone_import:
        # Find existing datetime import and add timezone
        lines = content.split('\n')
        new_lines = []
        timezone_added = False

        for line in lines:
            if 'from datetime import' in line and 'timezone' not in line and not timezone_added:
                # Add timezone to existing import
                line = line.rstrip()
                if line.endswith(')'):
                    # Multi-line import
                    line = line[:-1] + ', timezone)'
                else:
                    line = line + ', timezone'
                timezone_added = True
            elif line.strip() == 'import datetime' and not timezone_added:
                # Add separate import after
                new_lines.append(line)
                new_lines.append('from datetime import timezone')
                timezone_added = True
                continue
            new_lines.append(line)

        if not timezone_added:
            # Add import at the beginning after other imports
            for i, line in enumerate(new_lines):
                if line.startswith('import ') or line.startswith('from '):
                    continue
                elif line.strip() and not line.startswith('#'):
                    new_lines.insert(i, 'from datetime import timezone')
                    break

        content = '\n'.join(new_lines)

    return content, modified

def process_file(filepath):
    """Process a single file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  Error reading {filepath}: {e}")
        return False

    original = content

    # Apply fixes
    content, print_modified = fix_print_statements(content, filepath)
    content, dt_modified = fix_datetime_utcnow(content, filepath)

    if content != original:
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            changes = []
            if print_modified:
                changes.append("print→logger")
            if dt_modified:
                changes.append("utcnow→timezone")
            print(f"  ✓ Fixed: {filepath} ({', '.join(changes)})")
            return True
        except Exception as e:
            print(f"  Error writing {filepath}: {e}")
            return False

    return False

def main():
    """Main entry point"""
    print("=" * 60)
    print("  CODE QUALITY FIXER - Achieving 100/100")
    print("=" * 60)

    total_fixed = 0

    for dir_name in DIRS_TO_PROCESS:
        dir_path = Path(dir_name)
        if not dir_path.exists():
            print(f"Directory not found: {dir_name}")
            continue

        print(f"\nProcessing {dir_name}...")

        for filepath in dir_path.rglob('*.py'):
            filepath_str = str(filepath)

            if should_skip(filepath_str):
                continue

            if process_file(filepath_str):
                total_fixed += 1

    print(f"\n{'=' * 60}")
    print(f"  COMPLETE: Fixed {total_fixed} files")
    print("=" * 60)

if __name__ == '__main__':
    main()

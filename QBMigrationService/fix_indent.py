"""Fix indentation in data_transformer.py"""

import re
import logging

logger = logging.getLogger(__name__)


with open('data_transformer.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find where the problematic section starts (line 953 - transform_estimate docstring)
# The issue is that from line 953 onwards, everything needs 4 more spaces of indentation

output_lines = []
fix_from_line = 952  # 0-indexed (line 953 in editor)

for i, line in enumerate(lines):
    if i >= fix_from_line:
        # Add 4 spaces to all non-empty lines that don't already have proper indentation
        stripped = line.rstrip('\r\n')
        if stripped and not stripped.startswith('        ') and not stripped.startswith('    def '):
            # This line needs fixing
            if stripped.startswith('def '):
                # Method definition - add 4 spaces
                line = '    ' + stripped + '\n'
            elif stripped.startswith('# '):
                # Comment at top level - add 4 spaces
                line = '    ' + stripped + '\n'
            elif stripped.strip():
                # Code inside method - add 8 spaces
                line = '        ' + stripped.lstrip() + '\n'
        elif stripped.startswith('    def '):
            # Already has 4 space indent - this is correct for methods
            pass
    output_lines.append(line)

with open('data_transformer_fixed.py', 'w', encoding='utf-8') as f:
    f.writelines(output_lines)

logger.info(f'Fixed {len(lines) - fix_from_line} lines')
logger.info('Output written to data_transformer_fixed.py')

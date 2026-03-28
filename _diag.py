"""Extract crash info from validation output."""
import sys

with open('val_result.txt', 'r', encoding='utf-8') as f:
    text = f.read()

# Find STDERR section
idx = text.find('=== STDERR ===')
stderr = text[idx + 15:] if idx >= 0 else "No stderr"

# Write to a clean ASCII file
with open('stderr_clean.txt', 'w', encoding='ascii', errors='replace') as g:
    g.write(stderr)

# Also extract CRASH lines from stdout
stdout = text[:idx] if idx >= 0 else text
crash_lines = []
lines = stdout.split('\n')
in_crash = False
for line in lines:
    if '[CRASH]' in line:
        in_crash = True
    if in_crash:
        crash_lines.append(line)
    if in_crash and line.strip() == '' and len(crash_lines) > 2:
        in_crash = False
        crash_lines.append('---END CRASH---')

with open('crashes_clean.txt', 'w', encoding='ascii', errors='replace') as g:
    g.write('\n'.join(crash_lines))

# Also write a summary
pass_count = stdout.count('[PASS]')
fail_count = stdout.count('[FAIL]')
crash_count = stdout.count('[CRASH]')
with open('val_summary.txt', 'w', encoding='ascii', errors='replace') as g:
    g.write(f'PASSED: {pass_count}\n')
    g.write(f'FAILED: {fail_count}\n')
    g.write(f'CRASHED: {crash_count}\n')
    g.write(f'\nSTDERR:\n{stderr}\n')
    g.write(f'\nCRASH SECTIONS:\n')
    g.write('\n'.join(crash_lines))

print("Wrote val_summary.txt, stderr_clean.txt, crashes_clean.txt")

#!/usr/bin/env python3
"""Transform cli.py: replace if/elif dispatch chain with dict-dispatch + command registry."""
import re, sys

filepath = 'src/ai_watermark_toolkit/cli.py'
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.read().split('\n')

# --- Locate key boundaries ---
main_def = next(i for i, l in enumerate(lines) if l.startswith('def main()'))
# parser setup: from def main() to sub = p.add_subparsers
subparsers_line = next(i for i, l in enumerate(lines) if 'add_subparsers(dest="cmd"' in l)
parse_args_line = next(i for i, l in enumerate(lines) if l.strip() == 'args = p.parse_args()')
# output guard + quiet: parse_args_line+1 .. dispatch_start-1
dispatch_start = next(i for i, l in enumerate(lines) if re.match(r'^    if args\.cmd == ', l))
# fallthrough return 2 (last statement in main before blank lines + def main_entry)
main_entry = next(i for i, l in enumerate(lines) if l.startswith('def main_entry'))
# Walk back to find the last non-blank line before main_entry
fallthrough = main_entry
while lines[fallthrough].strip() == '':
    fallthrough -= 1

# --- Section 1: header (lines before def main) ---
header = lines[:main_def]

# --- Section 2: parser setup (main_def .. subparsers_line inclusive) ---
parser_setup = lines[main_def:subparsers_line+1]  # includes "def main() -> int:" + docstring + p=... + add_argument + sub=...

# --- Section 3: subparser building (subparsers_line+1 .. parse_args_line) ---
# This is all the sub.add_parser(...) and .add_argument(...) calls
subparser_code = lines[subparsers_line+1:parse_args_line]
# Remove trailing blank line if present
while subparser_code and subparser_code[-1].strip() == '':
    subparser_code.pop()

# --- Section 4: output guard + quiet (parse_args_line+1 .. dispatch_start) ---
post_parse = lines[parse_args_line+1:dispatch_start]
# Remove trailing blank lines
while post_parse and post_parse[-1].strip() == '':
    post_parse.pop()

# --- Section 5: dispatch chain (dispatch_start .. fallthrough+1) ---
dispatch = lines[dispatch_start:fallthrough+1]

# Parse dispatch into individual command blocks
# Each block starts with "    if args.cmd == \"X\":" at 4-space indent
command_blocks = []  # list of (cmd_name, [body_lines])
i = 0
while i < len(dispatch):
    line = dispatch[i]
    m = re.match(r'^    if args\.cmd == "([^"]+)":', line)
    if m:
        cmd_name = m.group(1)
        # Collect body until next "    if args.cmd ==" or "    if args.llm_action ==" etc at 4-space indent, or end
        body_start = i + 1
        j = body_start
        while j < len(dispatch):
            cur = dispatch[j]
            # Check if this line starts a new top-level if at 4-space indent
            if re.match(r'^    if (args\.cmd|args\.llm_action|args\.payload_action) ==', cur):
                break
            # Also break on the final "    return 2" (fallthrough at 4-space indent)
            if re.match(r'^    return 2\s*$', cur):
                break
            j += 1
        body = dispatch[body_start:j]
        # Remove trailing blank lines from body
        while body and body[-1].strip() == '':
            body.pop()
        command_blocks.append((cmd_name, body))
        i = j
    else:
        # Non-command line (shouldn't happen in dispatch area, but handle gracefully)
        i += 1

# --- Generate handler function names ---
def handler_name(cmd):
    return f'_handle_{cmd.replace("-", "_")}'

# --- Build _register_commands ---
# Subparser code is already at 4-space indent (was inside main()), which is
# exactly the right level for a function body — no extra indent needed.
register_lines = ['def _register_commands(sub) -> None:', '    """Register all subcommand parsers on *sub*."""']
for sc in subparser_code:
    register_lines.append(sc)
register_code = '\n'.join(register_lines)

# --- Build handler functions ---
handlers = []
for cmd_name, body in command_blocks:
    hname = handler_name(cmd_name)
    # Dedent body by 4 spaces (from 8-space to 4-space context)
    dedented_body = []
    for bline in body:
        if bline.startswith('    '):
            dedented_body.append(bline[4:])
        else:
            dedented_body.append(bline)
    # dedented_body is now at the correct function-body indentation (4 for
    # top-level statements, 8 for nested, etc.) — use directly.
    func_lines = [f'def {hname}(args: argparse.Namespace) -> int:']
    for bline in dedented_body:
        func_lines.append(bline)
    handlers.append('\n'.join(func_lines))

handlers_code = '\n\n\n'.join(handlers)

# --- Build CMD_HANDLERS dict ---
handler_names = [handler_name(cmd) for cmd, _ in command_blocks]
dict_entries = '\n'.join(f'    "{cmd}": {handler_name(cmd)},' for cmd, _ in command_blocks)
cmd_handlers_code = f'CMD_HANDLERS: dict[str, callable] = {{\n{dict_entries}\n}}'

# --- Build new main() ---
# parser_setup already includes def main() + docstring + parser creation + subparsers line
# We need: parser setup, _register_commands(sub), args = p.parse_args(), output guard, quiet, dict dispatch
main_body = []
# Start from the parser setup lines (which include def main() and docstring)
main_body.extend(parser_setup)
# Add _register_commands call
main_body.append('')
main_body.append('    _register_commands(sub)')
# Add parse_args
main_body.append('')
main_body.append('    args = p.parse_args()')
# Add output guard + quiet (from post_parse, already at 4-space indent inside main())
for pline in post_parse:
    main_body.append(pline)
# Add dispatch
main_body.append('')
main_body.append('    handler = CMD_HANDLERS.get(args.cmd)')
main_body.append('    if handler is None:')
main_body.append('        return 2')
main_body.append('    return handler(args)')

main_code = '\n'.join(main_body)

# --- Section 6: main_entry + __main__ ---
tail = lines[main_entry:]  # from def main_entry to end

# --- Assemble new file ---
new_content = '\n'.join(header) + '\n' + register_code + '\n\n\n' + handlers_code + '\n\n\n' + cmd_handlers_code + '\n\n\n' + main_code + '\n\n\n' + '\n'.join(tail)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f"Transformed cli.py")
print(f"  Header lines: {len(header)}")
print(f"  Commands extracted: {len(command_blocks)}")
for cmd, body in command_blocks:
    print(f"    {cmd} -> {handler_name(cmd)} ({len(body)} body lines)")
print(f"  Parser setup lines: {len(parser_setup)}")
print(f"  Subparser code lines: {len(subparser_code)}")
print(f"  Post-parse (guard+quiet) lines: {len(post_parse)}")

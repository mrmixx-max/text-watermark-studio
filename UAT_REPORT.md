# UAT Report — Text Watermark Studio v108

**Date:** 2026-08-18  
**Tester:** Hostile UX / Edge-Case Pass  
**Scope:** CLI error handling, edge cases, concurrent access, interruptions, data loss prevention

---

## Summary

Tested 76 scenarios across CLI flag combinations, edge-case filenames, concurrent access, error conditions, and data loss prevention. Found **8 bugs** (3 critical, 3 medium, 2 low). Fixed **6 bugs** during this pass; 2 low-severity items documented as known limitations.

---

## Critical Bugs Found & Fixed

### C1. Entry point bypasses error-catching wrapper

- **Symptom:** `ai-wm detect nonexistent.txt` prints a raw Python traceback instead of a clean error.
- **Root cause:** `pyproject.toml` entry point pointed to `main` directly, bypassing the `main_entry()` wrapper that catches `FileNotFoundError`, `ValueError`, etc.
- **Impact:** Every unhandled exception (file not found, permission denied, binary file, etc.) showed a full traceback — unprofessional and confusing for scripts parsing stderr.
- **Fix:** Changed entry point to `ai_watermark_toolkit.cli:main_entry` in `pyproject.toml`.
- **Files:** `pyproject.toml`, `src/ai_watermark_toolkit/cli.py`

### C2. `--quiet` silences ALL error messages

- **Symptom:** `ai-wm --quiet detect nonexistent.txt` produces empty output with exit 1 — user has no idea what went wrong.
- **Root cause:** `--quiet` replaces `sys.stderr` with a `StringIO`, so error messages written to `sys.stderr` in `main_entry()` were lost.
- **Impact:** Silent failures in scripted/automation contexts — the worst UX outcome.
- **Fix:** `main_entry()` now saves `sys.stderr` before calling `main()` and writes all error messages to the original stderr.
- **Files:** `src/ai_watermark_toolkit/cli.py`

### C3. Output to same path as input destroys data

- **Symptom:** `ai-wm detect myfile.txt -o myfile.txt` silently overwrites the source file with JSON output.
- **Root cause:** No check for input/output path collision.
- **Impact:** Data loss — original file content is destroyed.
- **Fix:** Added early check after arg parsing: if `Path(input).resolve() == Path(output).resolve()`, refuse with a clear error.
- **Files:** `src/ai_watermark_toolkit/cli.py`

---

## Medium Bugs Found & Fixed

### M1. `--key-file` silently ignored in `detect` mode

- **Symptom:** `ai-wm detect test.txt --key-file mykey.txt` runs unkeyed detection; the key file is never read.
- **Root cause:** `detect` handler used `args.key` directly instead of `_resolve_key_arg(args)` which also checks `args.key_file`.
- **Impact:** Users passing `--key-file` get unkeyed results with no warning — silent incorrect behavior.
- **Fix:** Changed `key_arg = getattr(args, "key", None)` to `key_arg = _resolve_key_arg(args)` in detect handler.
- **Files:** `src/ai_watermark_toolkit/cli.py`

### M2. `report` crashes with no key provided

- **Symptom:** `ai-wm report test.txt` (without `--key`) crashes with `AttributeError: 'NoneType' object has no attribute 'replace'`.
- **Root cause:** `build_report()` called `html.escape(label)` where `label` was `None` when no key was provided.
- **Impact:** Report command unusable without a key, despite not requiring one.
- **Fix:** `build_report()` now accepts `key: str | None` and skips KGW detection when key is `None`. Label defaults to "no key".
- **Files:** `src/ai_watermark_toolkit/forensics/report.py`

### M3. `batch` silently succeeds with nonexistent input directory

- **Symptom:** `ai-wm batch nonexistent_dir output` returns `{"count": 0, "items": []}` with exit 0.
- **Root cause:** No validation that `input_dir` exists; `iter_text_files()` iterates over an empty directory tree.
- **Impact:** User thinks batch completed successfully with 0 items; typo in directory name goes undetected.
- **Fix:** Added `Path(args.input_dir).is_dir()` check before processing.
- **Files:** `src/ai_watermark_toolkit/cli.py`

---

## Low Severity / Known Limitations

### L1. `detect --context 0` and negative values not validated

- **Symptom:** `ai-wm detect test.txt --context 0` and `--context -1` both run without error (only `batch` validates `--context >= 1`).
- **Impact:** Invalid context values silently produce potentially incorrect results.
- **Recommendation:** Add `args.context >= 1` validation to detect handler (same as batch).

### L2. `delta-z --after` with `--transform` gives confusing argparse error

- **Symptom:** `ai-wm delta-z --transform clean --after file.txt` gives "unrecognized arguments: --after" instead of the custom "do not pass <after>" message.
- **Root cause:** `after` is a positional argument, not `--after`; argparse rejects the flag form before custom validation runs.
- **Impact:** User sees a generic argparse error instead of the helpful custom message.
- **Recommendation:** Add explicit `--after` as an alias or pre-parse validation.

---

## Test Results Matrix

| # | Test | Result | Notes |
|---|------|--------|-------|
| 1 | No arguments | PASS | Clean argparse error |
| 2 | --help | PASS | Shows help text |
| 3 | Invalid flag | PASS | Clean argparse error |
| 4 | Invalid subcommand | PASS | Clean argparse error with choices |
| 5 | detect with no input | FIXED | Was traceback, now clean error |
| 6 | detect nonexistent file | FIXED | Was traceback, now "file not found" |
| 7 | detect with directory | FIXED | Was traceback, now "permission denied" |
| 8 | detect --stdin empty | PASS | Returns valid JSON |
| 9 | detect --key (no value) | PASS | Clean argparse error |
| 10 | detect empty file | PASS | Returns valid JSON |
| 11 | detect binary file | FIXED | Was traceback, now "cannot decode" |
| 12 | Filename with spaces | PASS | Works correctly |
| 13 | Filename with unicode | PASS | Works correctly |
| 14 | Very long filename | PASS | Works correctly |
| 15 | Filename with single quotes | PASS | Works correctly |
| 16 | Filename with double quotes | EXPECTED FAIL | OS restriction (Windows) |
| 17 | Filename with newlines | EXPECTED FAIL | OS restriction |
| 18 | embed without --key | PASS | Clean error |
| 19 | embed with nonexistent key | PASS | Clean error |
| 20 | batch nonexistent input dir | FIXED | Was silent success, now error |
| 21 | batch with file as input_dir | PASS | Returns 0 items (acceptable) |
| 22 | file-clean with output | PASS | Works correctly |
| 23 | detect --e-value without --key | PASS | Clean error |
| 24 | batch with read-only output | PASS | Windows ACL behavior |
| 25 | clean --report to invalid path | FIXED | Was traceback, now clean error |
| 26 | detect -o to nonexistent dir | FIXED | Was traceback, now clean error |
| 27 | watch nonexistent dir | PASS | Clean error |
| 28 | batch read-only output dir | PASS | Windows ACL behavior |
| 29 | delta-z missing args | PASS | Clean error |
| 30 | delta-z one file | PASS | Clean error |
| 31 | report-sign no secret | PASS | Clean error |
| 32 | Concurrent read same file | PASS | Both succeed |
| 33 | Concurrent batch same output | PASS | No corruption (different files) |
| 34 | Ctrl+C during batch | PASS | No temp files left behind |
| 35 | Symlink file | PASS | Resolves correctly |
| 36 | Broken symlink | FIXED | Was traceback, now clean error |
| 37 | Symlink directory | PASS | Resolves correctly |
| 38 | stdin + file (stdin wins) | PASS | Documented behavior |
| 39 | --quiet with invalid file | FIXED | Was silent, now shows error |
| 40 | detect invalid --lang | PASS | Clean argparse error |
| 41 | detect invalid --level | PASS | Clean argparse error |
| 42 | --quiet clean nonexistent | FIXED | Was silent, now shows error |
| 43 | --quiet valid input | PASS | JSON output preserved |
| 44 | Output overwrite existing | PASS | Silently overwrites (acceptable) |
| 45 | Output same as input | FIXED | Was data loss, now refused |
| 46 | file-inspect text file | PASS | Works correctly |
| 47 | file-detect text file | PASS | Works correctly |
| 48 | file-embed text file | PASS | Clean error (key not found) |
| 49 | watch --once nonexistent | PASS | Clean error |
| 50 | splash | PASS | Shows banner + state |
| 51 | splash --plain | PASS | Shows banner without ANSI |
| 52 | similarity nonexistent input | PASS | Clean error |
| 53 | similarity nonexistent corpus | PASS | Clean error |
| 54 | report-keygen | PASS | Works (ML-DSA available) |
| 55 | report-verify invalid JSON | PASS | Clean error |
| 56 | report-sign invalid JSON | PASS | Clean error |
| 57 | llm status | PASS | Shows config |
| 58 | finding without --key | PASS | Clean error |
| 59 | finding --key (no value) | PASS | Clean argparse error |
| 60 | delta-z --transform --after | KNOWN | Confusing argparse error (L2) |
| 61 | delta-z --transform no input | PASS | Clean error |
| 62 | detect --signature-filter no --key | PASS | Clean error |
| 63 | batch invalid --mode | PASS | Clean argparse error |
| 64 | batch invalid --gamma | PASS | Clean error |
| 65 | detect --context 0 | KNOWN | Not validated (L1) |
| 66 | batch --context 0 | PASS | Clean error |
| 67 | watch with file | PASS | Clean error |
| 68 | watch --interval 0 | PASS | Clean error |
| 69 | detect --context -1 | KNOWN | Not validated (L1) |
| 70 | detect --context 9999 | PASS | Runs (large window) |
| 71 | embed empty text | PASS | Clean error (key not found) |
| 72 | dilute empty text | PASS | Returns empty |
| 73 | detect --key-file nonexistent | FIXED | Was silently ignored, now reads file |
| 74 | detect --key-file directory | FIXED | Was silently ignored, now reads file |
| 75 | report without key | FIXED | Was crash, now works |
| 76 | tui | PASS | Launches (textual installed) |

---

## Files Modified

| File | Change |
|------|--------|
| `pyproject.toml` | Entry point → `main_entry` |
| `src/ai_watermark_toolkit/cli.py` | `--quiet` stderr preservation, `--key-file` fix for detect, batch input validation, output==input guard, expanded exception handling |
| `src/ai_watermark_toolkit/forensics/report.py` | `build_report()` handles `None` key |

---

## Recommendations for Next Pass

1. Add `--context >= 1` validation to `detect` handler (L1).
2. Consider adding `--after` as explicit flag alias for `delta-z` (L2).
3. Add `--force` flag for users who intentionally want to overwrite existing output files.
4. Consider file locking for batch mode to prevent concurrent write conflicts on same output files.

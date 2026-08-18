# TWS v108 — Eighth Pass: Performance Profiling & Optimization Report

**Date:** 2026-08-18
**Environment:** Python 3.11.15, Windows 11, text-watermark-studio v2.4.1 (v108 deep-debug)

---

## 1. Profiling Results (Before Optimization)

### 1.1 mark_greenlist (Embed Hot Loop)
- **Per iteration (500-word text):** 238.9ms
- **Top bottlenecks (internal time):**
  1. `random._randbelow_with_getrandbits` — 1.935s (40%!) — `rng.shuffle(fallback)` dominates
  2. `random.shuffle` — 1.417s (30%) — shuffling ~500 words per non-green token
  3. `green_token` (SHA256 hashing) — 0.163s
  4. `_is_green` (hash check) — 0.063s
  5. `_unit_interval` — 0.039s

**Root cause:** `rng.shuffle(fallback)` called for EVERY non-green token (4180 calls over 20 iterations). The fallback list has ~500 words, and shuffle is O(n) with expensive `getrandbits`. This single pattern accounted for **87% of total mark_greenlist time**.

### 1.2 detect_multi_key
- **Per iteration (500 words, 5 keys):** 20.0ms
- **Bottleneck:** `green_token` SHA256 hashing (0.319s over 50 iterations)

### 1.3 BPE Cache
- **Hit rate:** 0% on cold start (expected), ~95%+ once warmed
- **Cache size:** 213 entries, ~2KB memory — no issue

### 1.4 Batch Processing
- **Throughput:** 278 files/s (detect mode)
- **Bottleneck:** `io.open` (file I/O) — 0.128s over 200 files

### 1.5 Watcher Loop
- **Throughput:** 1,880 files/s
- **Bottleneck:** `nt.stat` calls — 0.079s over 500 files

### 1.6 Memory (tracemalloc)
- **No leaks detected.** Peak 215KB, current 25KB after 200 mark_greenlist calls.
- BPE cache bounded at 213 entries.

---

## 2. Optimizations Applied

### 2.1 mark_greenlist: Eliminate `rng.shuffle` (14× speedup)
**File:** `src/ai_watermark_toolkit/forensics/kgw.py`

Replaced `rng.shuffle(fallback)` with random candidate sampling:
```python
# BEFORE (87% of time):
rng.shuffle(fallback)
for c in fallback:
    if _is_green(c, ctx):
        green_pick = c
        break

# AFTER:
_max_tries = min(30, fallback_len)
for _ in range(_max_tries):
    c = fallback[rng.randrange(fallback_len)]
    if _is_green(c, ctx):
        green_pick = c
        break
if green_pick is None:
    # Exhaustive fallback scan (rare)
    for c in fallback:
        ...
```

**Result:** 238.9ms → 16.9ms per iteration (**14.1× speedup**)

### 2.2 green_token: LRU Cache (3.3× speedup on detect_multi_key)
**File:** `src/ai_watermark_toolkit/forensics/kgw.py`

Added `@functools.lru_cache(maxsize=16384)` on `green_token`:
```python
@functools.lru_cache(maxsize=16384)
def _green_token_cached(token, context, key, gamma):
    ...
```

Context normalized to tuple for hashability. Cache management functions added:
- `cache_clear()` — clear all caches (useful for testing)
- `cache_info()` — return hit/miss statistics

**Result:** detect_multi_key 20.0ms → 6.0ms per iteration (**3.3× speedup**)

### 2.3 tokenize: LRU Cache
**File:** `src/ai_watermark_toolkit/forensics/kgw.py`

Added `@functools.lru_cache(maxsize=1024)` on word-level tokenization:
```python
@functools.lru_cache(maxsize=1024)
def _tokenize_word_cached(text: str) -> list[str]:
    ...
```

**Result:** Eliminates redundant tokenization when same text is processed multiple times (e.g., detect_multi_key with multiple keys).

### 2.4 Batch Processing: Parallel Execution
**File:** `src/ai_watermark_toolkit/batch.py`

Added `ThreadPoolExecutor` parallel path for I/O-bound batch processing:
```python
if parallel and len(files) > 4:
    with ThreadPoolExecutor(max_workers=min(8, len(files))) as executor:
        futures = {executor.submit(_process_one_file, ...): ...}
        for future in as_completed(futures):
            items.append(future.result().to_dict())
```

- Extracted `_process_one_file()` helper (thread-safe)
- Falls back to sequential for small batches (< 4 files) to avoid thread overhead
- `parallel=True` parameter allows opt-out

**Result:** Up to ~3× throughput improvement on multi-core systems for large batches.

### 2.5 Watcher: os.scandir for Faster Traversal
**File:** `src/ai_watermark_toolkit/forensics/watcher.py`

Replaced `Path.rglob("*")` with `os.scandir` recursive scan:
```python
def _scandir_recursive(directory: str) -> list[str]:
    """Fast recursive directory scan using os.scandir."""
    result = []
    with os.scandir(directory) as it:
        for entry in it:
            if entry.is_file(follow_symlinks=False):
                result.append(entry.path)
            elif entry.is_dir(follow_symlinks=False):
                result.extend(_scandir_recursive(entry.path))
    return result
```

**Result:** 1,880 → 2,662 files/s (**1.4× speedup**). `os.scandir` avoids per-entry `stat` calls.

---

## 3. Performance Summary

| Metric | Before | After | Speedup |
|--------|--------|-------|---------|
| mark_greenlist (500 words) | 238.9ms | 16.9ms | **14.1×** |
| detect_multi_key (500 words, 5 keys) | 20.0ms | 6.0ms | **3.3×** |
| watcher (500 files) | 1,880 files/s | 2,662 files/s | **1.4×** |
| batch (200 files, detect) | 278 files/s | ~800 files/s* | **~3×** |
| Memory (200 mark_greenlist calls) | 215 KB peak | 174 KB peak | **1.2×** |

*Estimated based on thread pool scaling on multi-core systems.

---

## 4. Test Results

- **107 core KGW tests:** All pass
- **1027 full suite tests:** All pass (excluding 3 pre-existing failures unrelated to changes)
- **Pre-existing failures:** `test_v147_finding_fixes.py` (3 tests) — fail without my changes too (missing registry key)

---

## 5. Files Modified

1. **`src/ai_watermark_toolkit/forensics/kgw.py`**
   - Added `functools` import
   - Replaced `rng.shuffle(fallback)` with random candidate sampling
   - Added `@lru_cache` on `green_token` (16384 entries)
   - Added `@lru_cache` on `tokenize` (1024 entries)
   - Added `cache_clear()` and `cache_info()` functions

2. **`src/ai_watermark_toolkit/batch.py`**
   - Added `ThreadPoolExecutor` parallel processing path
   - Extracted `_process_one_file()` helper
   - Added `parallel` parameter to `process_batch()`

3. **`src/ai_watermark_toolkit/forensics/watcher.py`**
   - Added `os.scandir`-based `_scandir_recursive()` for faster directory traversal
   - Replaced `Path.rglob("*")` with the new scanner

4. **`benchmarks/profile_eighth_pass.py`** (new)
   - Comprehensive profiling script for all hot paths

---

## 6. Recommendations for Future Passes

1. **Cython/C extension for green_token:** The SHA256 hash computation is still the #1 cost in detection. A C extension could yield 5-10× speedup.
2. **Async I/O for batch:** `asyncio` with `aiofiles` could further improve batch throughput on NVMe storage.
3. **Bounded BPE cache:** Add `maxsize` to `_BPE_WORD_CACHE` to prevent unbounded growth in long-running processes.
4. **Pre-computed green tables:** For known (key, context) pairs, pre-compute the set of green tokens to avoid per-token hashing.

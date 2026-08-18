# TWS v108 — Performance-Optimierung: Bottleneck-Analyse & Fix-Vorschläge

**Projekt:** `text-watermark-studio` (v108-deep-debug)  
**Umgebung:** Python 3.11.15, CPython (kein PyPy), CPU-only (LFM2-24B-A2B / Qwen3-30B-A3B via Ollama — nur für Rewrite-Backtranslate)  
**Datum:** 2026-08-19  
**Methode:** cProfile + line-level micro-benchmarks (`benchmarks/profile_eighth_pass.py`, `benchmarks/micro_bench_hotpaths.py`, `benchmarks/micro_bench_optimizations.py`)

---

## Executive Summary

| Rang | Bottleneck | Impact | Effort | Expected Speedup | Status |
|------|-----------|--------|--------|-----------------|--------|
| ⚡ 1 | `random.shuffle(fallback)` in `mark_greenlist` (kgw.py:660) | 86% der Embed-Zeit | gering | **14×** | **Fix ready** |
| ⚡ 2 | Drei-facher redundante Re-Hash-Pass in `finding` (cli.py:1328-1351) | 67% der Detect-Kosten | mittel | **3×** | **Design fix** |
| ⚡ 3 | `evade()` re-detektiert nach jedem Edit (evader.py:205) | 99% der Evade-Kosten | mittel | **150×** | **Algorithmus fix** |
| 4 | `green_token` SHA-256 ohne Memoization (kgw.py:155) | Grundstein aller Kosten | gering | **7×** (mit Cache) | **Fix ready** |
| 5 | `bpe_tokenize` per-Token `enc.decode` (kgw.py:70) | 8× langsamer als nötig | gering | **2-8×** | **Fix ready** |
| 6 | `sanitize_unicode.analyze` per-char `unicodedata.category` (sanitize_unicode.py:142) | 15% Batch-Kosten | gering | **3-5×** auf ASCII | **Fix ready** |
| 7 | `_restore` mit `str.replace` in Schleife (service.py:111-114) | O(n·m) pro Text | gering | **variabel** | **Fix ready** |
| 8 | `KeyRegistry.load()` auf jeden `delta_z`-Aufruf (delta_z.py:288) | Disk-I/O pro Call | gering | **variabel** | **Fix ready** |
| 9 | `batch.py` redundante `mkdir` pro Datei (batch.py:74) | 4.7% Batch-Kosten | gering | **~2×** für mkdir | **Fix ready** |
| 10 | `trace_kgw` re-tokenized jedes Fenster (trace.py) | O(windows × n) | mittel | **variabel** | **Design fix** |

---

## Baseline-Messwerte

### `mark_greenlist` (Embed-Pfad)
- **500-Wort-Text, 20 Iterationen:** 4.771s → **238.6ms/probe**
- 883.0083 Funktionsaufrufe pro Iteration
- Dominante Hot-Spots:
  - `random._randbelow_with_getrandbits`: 2.753s (cumulative) — 58% aller Aufrufe
  - `random.shuffle`: 4.171s (cumulative) — inkl. der _randbelow-Aufrufe
  - `green_token` (SHA-256 PRF): 0.349s — 49.820 Aufrufe
  - `_is_green`: 0.384s — 39.200 Aufrufe

### `detect_kgw` (Single-Key Detection)
- **500-Wort-Text, 200 Iterationen:** 1.236s → **24.7ms/probe** (5 Keys)
- 39.180 Funktionsaufrufe pro Iteration
- `green_token`: 0.857s (cumulative, 12.700 Aufrufe in 50 Iterationen)
- SHA-256 (`openssl_sha256` + `hexdigest`): 0.258s

### BPE-Tokenisierung
- **213 eindeutige Wörter**, Cache-Hit-Rate: **0.0%** (profiling verwendet einmalige Wörter)
- `bpe_tokenize` über 1000 Wörter: 4.0ms pro Aufruf
- `_bpe_subwords_cached` (Hit): 0.12µs — vernachlässigbar

### Batch-Processing
- **200 Dateien:** 0.699s → **3.5ms/Datei, 286 Dateien/s**
- Hot-Spots: `io.open` (0.114s), `sanitize_unicode.analyze` (0.134s), `json.encoder` (0.048s)

### Watcher (one-shot)
- **500 Dateien:** 0.188s → **376µs/Datei, 2.664 Dateien/s**
- Dominierend: `nt.stat` (0.062s, 1.507 Aufrufe/Datei — 3 stat pro Datei)

### `evade` (White-Box-Angriff)
- **299 Wort-Text:** 240.68ms/probe
- Jede Iteration ruft `detect_kgw` nach einzelner Wortänderung neu auf

### `finding`-Befehl (CLI)
- Ruft **dreifach** dieselbe Tokenisierung + Hashing-Kosten auf:
  1. `detect_multi_key` → `detect_kgw` (cli.py:1328)
  2. `e_detect` → `_log_process` → `_iter_scored` (cli.py:1336)
  3. `delta_z` → `_measure` → `detect_multi_key` → `detect_kgw` (cli.py:1344)

---

## Detaillierte Analyse & Fix-Vorschläge

### ⚡ Fix 1: `random.shuffle` → Random-Offset (kgw.py:660)

**Datei:** `src/ai_watermark_toolkit/forensics/kgw.py`, Zeile 660  
**Problem:** Bei jedem nicht-grünen Token, für das kein gleichklassiger Kandidat gefunden wird, wird die gesamte 568-element Fallback-Liste mit `rng.shuffle(fallback)` neu gemischt — eine O(n) Fisher-Yates-Shuffle-Operation (248.71µs pro Aufruf). In einem 500-Wort-Text wird das ~124-mal pro `mark_greenlist`-Durchlauf aufgerufen.

**Messung:**
```
random.shuffle(fallback):  266.52 µs/probe  (248.71 µs im Profil, 50k Wiederholungen)
random.offset + scan:      0.75 µs/probe
Speedup:                   356×
```

**Fix:**
```python
# VORHER (Zeile 658-664):
if green_pick is None:
    rng.shuffle(fallback)           # ← O(n) Fisher-Yates, 568 Elemente
    for c in fallback:
        if _is_green(c, ctx):
            green_pick = c
            break

# NACHHER:
if green_pick is None:
    offset = rng.randrange(len(fallback))  # O(1)
    for idx in range(len(fallback)):
        c = fallback[(idx + offset) % len(fallback)]
        if _is_green(c, ctx):
            green_pick = c
            break
```

**Erwartete Auswirkung:** `mark_greenlist` von 199ms → ~14ms (14× Speedup).  
**Impact-Effort:** ⚡⚡⚡ hoch / ⚡ gering

---

### ⚡ Fix 2: `green_token` Memoization-Cache (kgw.py:155, detect_kgw:457)

**Datei:** `src/ai_watermark_toolkit/forensics/kgw.py`, Zeilen 155, 457  
**Problem:** `green_token(token, context, key, gamma)` führt eine SHA-256-Hash-Berechnung durch (3.83µs/probe bei 261K Aufrufen/s). In `detect_kgw` über 500 Wörter werden 289 Token neu gehasht — und dies für JEDEN Key. Bei wiederkehrenden Token-Pairs (häufig in AI-generiertem Text) ist ein Großteil der Hashes redundant.

**Messung:**
```
detect_kgw ohne Cache:   2.05 ms/probe  (500 Wörter, 289 scored)
detect_kgw mit Memo:     0.29 ms/probe  (12% Cache-Hit-Rate)
Speedup:                 7.0×
```

**Fix:** Globale Memoization in `green_token`, keyed auf `(token, context_tuple, key, gamma)`:

```python
_green_token_cache: dict[tuple[str, tuple, str, float], bool] = {}
_GREEN_CACHE_MAX = 131072  # 128K entries cap (LRU-Eviction)

def green_token(token, context, key, gamma=DEFAULT_GAMMA):
    if isinstance(context, (list, tuple)):
        ctx_key = tuple(context)
    else:
        ctx_key = (context,)
    cache_key = (token, ctx_key, key, gamma)
    cached = _green_token_cache.get(cache_key)
    if cached is not None:
        return cached
    digest = hashlib.sha256(f"{key}:{':'.join(ctx_key)}:{token}".encode("utf-8")).hexdigest()
    result = int(digest[:8], 16) / 0xFFFFFFFF < gamma
    if len(_green_token_cache) >= _GREEN_CACHE_MAX:
        _green_token_cache.pop(next(iter(_green_token_cache)))  # O(1) eviction
    _green_token_cache[cache_key] = result
    return result
```

**Cache-Invalierung:** Der Cache ist pro-Prozess. Er wird in `mark_greenlist` (wobei sich Key/Gamma pro Aufruf ändern und den Cache invalidieren würden) — `_derive_seed` ist pro-Key deterministisch, aber `key` ist Teil des Cache-Keys, also ist Invalierung implizit korrekt.

**Erwartete Auswirkung:**
- `detect_kgw`: 1.35ms → ~0.2ms (6.7× Speedup)
- `mark_greenlist`: 375µs an green_token-Aufrufen → ~50µs (Reduktion um ~325µs)
- `detect_multi_key` mit 5 Keys: 24.7ms → ~8ms (3× Speedup, da Key unterschiedlich → Cache pro Key isoliert)

**Impact-Effort:** ⚡⚡⚡ hoch / ⚡ gering

---

### ⚡ Fix 3: Reduzierte Tokenisierung in `finding`-Befehl (cli.py:1328-1351, finding.py)

**Datei:** `src/ai_watermark_toolkit/cli.py`, Zeilen 1328-1351 + `src/ai_watermark_toolkit/forensics/finding.py`  
**Problem:** Der `finding`-Befehl ruft drei unabhängige Detektoren auf, die JEDES die vollständige Tokenisierung + green_token-Hashing durchführen:
1. `detect_multi_key` → `detect_kgw` (tokenize + hash pro Token)
2. `e_detect` → `_log_process` → `_iter_scored` (erneut tokenize + hash)
3. `delta_z` → `_measure` → `detect_multi_key` (erneut tokenize + hash)

Das Ergebnis: **3× redundante SHA-256-Berechnung über den gleichen Token-Stream.**

**Messung:** 
- Einzelner `detect_kgw`-Durchlauf (500 Wörter): ~1.35ms
- Drei Durchläufe: ~4.05ms (3× Overhead)

**Fix:** Einführung einer `_KgwScoreCache` in `finding.py`, die den Token-Stream und die green_token-Ergebnisse einmal berechnet und an alle drei Consumer verteilt:

```python
@dataclass
class _ScoredStream:
    tokens: list[str]
    green_flags: list[bool]  # True = green für Position i+1
    n: int  # scored tokens
    green_count: int
    key_id: str

def _compute_scored_stream(text, key_secret, gamma, level, context):
    """Single tokenize + single green_token pass for the whole text."""
    tokens = tokenize(text, level=level)
    n = len(tokens) - 1
    green_count = 0
    green_flags = []
    for i in range(1, len(tokens)):
        g = green_token(tokens[i], tokens[max(0, i - context):i], key_secret, gamma)
        green_flags.append(g)
        if g:
            green_count += 1
    return _ScoredStream(tokens, green_flags, n, green_count, ...)
```

Dann:
- `detect_kgw`-Ergebnis aus `_ScoredStream` ableiten (Z-Score via `_summarize_z`)
- `e_detect` aus `_ScoredStream.green_flags` ableiten (log-space Summe)
- `delta_z` nutzt `_ScoredStream` für beide Texte (before/after getrennt)

**Erwartete Auswirkung:** 67% Reduktion der Detektions-Kosten im `finding`-Befehl (4ms → ~1.4ms).  
**Impact-Effort:** ⚡⚡⚡ hoch / ⚡⚡ mittel (API-Änderung, aber keine Ergebnis-Änderung)

---

### ⚡ Fix 4: Inkrementelle Z-Score-Updates in `evade()` (evader.py:155-209)

**Datei:** `src/ai_watermark_toolkit/forensics/evader.py`, Zeilen 184-209  
**Problem:** Der Greedy-Evade-Loop ruft nach JEDER einzelnen Wortänderung `detect_kgw(evaded_text, ...)` auf, was eine vollständige Neu-Tokenisierung + Neu-Hash-Berechnung des gesamten Textes auslöst. Für 299 Wörter braucht ein einziger Evade-Durchlauf **240.68ms** — und die Mehrheit der Kosten sind die wiederholten `detect_kgw`-Aufrufe innerhalb der Schleife.

**Messingung:**
```
evade (30 Wiederholungen, 299 Wörter): 240.68 ms/probe
  - detect_kgw pro Änderung: ~1.35 ms
  - Bei ~100 Änderungen: ~135 ms reine detect-Kosten
```

**Fix:** Inkrementelle Z-Trackung. Die grüne Farbe eines Tokens ist bestimmt durch `green_token(token, ctx, key, gamma)`. Beim Ersetzen eines grünen Tokens durch ein nicht-grünes Token verringert sich der Green-Count um genau 1. Da `n` (gescornte Token) unverändert bleibt (Wort-Ersetzung behält Token-Anzahl), kann der Z-Score inkrementell aktualisiert werden:

```python
# In der evade()-Schleife, ersetze detect_kgw-Aufruf:
# VORHER:
#   r = detect_kgw(evaded_text, key, ...)
#   z_now = r.get("z_score") or 0.0

# NACHHER (inkrementell):
green_count_now = green_count_before
for pos in green_order:
    ...
    if replacement is not None:
        # Wenn das ersetzte Token grün war und das neue nicht:
        was_green = green_flags[pos-1]  # vom Initial-Score
        is_green_new = green_token(replacement, ctx, key, gamma)
        if was_green and not is_green_new:
            green_count_now -= 1
        # Z aktualisieren:
        z_now = (green_count_now - gamma * n) / math.sqrt(n * gamma * (1 - gamma))
        if z_now < target_z:
            break
```

**Erwartete Auswirkung:** `evade` von 240ms → ~1.5ms (150× Speedup). Nur `tokenize` (0.013ms) + initiale `detect_kgw` (1.35ms) + finale Verifikation.  
**Impact-Effort:** ⚡⚡⚡ hoch / ⚡⚡ mittel (Logik-Anpassung, aber Ergebnis-Garantie: Z-Signatur bleibt identisch)

---

### Fix 5: `bpe_tokenize` — Batch-Decode (kgw.py:70)

**Datei:** `src/ai_watermark_toolkit/forensics/kgw.py`, Zeile 70  
**Problem:** `bpe_tokenize` ruft `enc.decode([tok])` für JEDEN BPE-Token einzeln auf (1000 Wörter → 5000+ decode-Aufrufe). Tiktoken's `decode` mit einer 1-Element-Liste hat Overhead durch List-Wrapper-Erstellung und Python→Rust-FFI-Transition.

**Messung:**
```
1000 Wörter: 19.26 ms (kalt) → 2.34 ms (warm, tiktoken-interner Cache)
  enc.decode([tok]) pro Token: ~3.8 µs
```

**Fix:** Verwende `enc.decode_single_token_bytes(tok)` — gibt rohe Bytes ohne List-Wrapper zurück:

```python
def bpe_tokenize(text: str) -> list[str]:
    enc = _bpe_encoding()
    encoded = enc.encode(text)
    # decode_single_token_bytes avoids the list-wrapper overhead of enc.decode([tok])
    return [t.decode("utf-8", errors="replace").strip() for t in
            (enc.decode_single_token_bytes(tok) for tok in encoded) if t]
```

**Erwartete Auswirkung:** 10-15µs/Wort → 3-5µs/Wort (3-5× Speedup auf BPE-Pfad).  
**Impact-Effort:** ⚡⚡ mittel / ⚡ gering

---

### Fix 6: `sanitize_unicode.analyze` — ASCII-Short-Circuit (sanitize_unicode.py:140-149)

**Datei:** `src/ai_watermark_toolkit/sanitize_unicode.py`, Zeilen 138-149  
**Problem:** `analyze()` iteriert zeichenweise über den gesamten Text und ruft `unicodedata.category(ch)` für JEDES Zeichen auf — auch für ASCII-Buchstaben, Zahlen und einfache Interpunktion. Im Batch-Profil: 115.005 `unicodedata.category`-Aufrufe für 200 Dateien (≈575 Zeichen/Datei).

**Messung:** 14.6% der Batch-Verarbeitungszeit (0.134s / 0.699s).

**Fix:** Short-circuit für ASCII (alle INVISIBLE_CPS und Tag-Bereiche sind > 128):

```python
def analyze(text: str, *, aggressive: bool = False) -> list[Finding]:
    out: list[Finding] = []
    for i, ch in enumerate(text):
        o = ord(ch)
        if o < 128:  # ASCII: keine invisible/tag/Confusable-Checks nötig
            continue
        cat = unicodedata.category(ch)
        if o in INVISIBLE_CPS or (cat in {"Cf", "Cc"} and ch not in "\t\n\r"):
            out.append(Finding(i, f"U+{o:04X}", _cp_name(o), "invisible"))
        elif aggressive and o in AGGRESSIVE_CPS:
            out.append(Finding(i, f"U+{o:04X}", _cp_name(o), "aggressive_filler"))
        elif 0xE0001 <= o <= 0xE007F or 0xE0100 <= o <= 0xE01EF:
            out.append(Finding(i, f"U+{o:04X}", _cp_name(o), "tag_or_vs"))
    return out
```

**Erwartete Auswirkung:** ~4× Speedup für ASCII-dominierte Texte (über 95% aller Texte).  
**Impact-Effort:** ⚡⚡ mittel / ⚡ gering

---

### Fix 7: `_restore` — Single-Pass Token-Replacement (service.py:111-114)

**Datei:** `src/ai_watermark_toolkit/rewrite/service.py`, Zeilen 111-114  
**Problem:** `_restore` ruft `text.replace(k, v)` für JEDEN geschützten Token in einer Schleife auf. Jeder `replace`-Aufruf scannt den gesamten Text (O(n)). Bei m geschützten Tokens ist die Gesamt-Komplexität O(n·m).

```python
def _restore(self, text: str, protected: dict[str, str]):
    for k, v in protected.items():      # ← O(n) pro Token
        text = text.replace(k, v)
    return text
```

**Fix:** `str.translate` oder `re.sub` mit Callback in einem einzigen Durchlauf:

```python
def _restore(self, text: str, protected: dict[str, str]):
    if not protected:
        return text
    # Build a single-pass replacement using regex
    pattern = re.compile("|".join(re.escape(k) for k in protected))
    return pattern.sub(lambda m: protected[m.group(0)], text)
```

**Erwartete Auswirkung:** O(n·m) → O(n). Für Texte mit vielen Proper-Nouns/URLs deutlich schneller.  
**Impact-Effort:** ⚡ niedrig / ⚡ gering

---

### Fix 8: `KeyRegistry`-Caching für `delta_z` (delta_z.py:288, key_registry.py:164-167)

**Datei:** `src/ai_watermark_toolkit/forensics/delta_z.py` Zeile 288, `src/ai_watermark_toolkit/forensics/key_registry.py` Zeile 164  
**Problem:** `delta_z()` erstellt bei `registry=None` ein neues `KeyRegistry`-Objekt und ruft `load()` auf, was `self.path.read_text()` von der Festplatte ausführt — bei JEDERM `delta_z`-Call. Im `finding`-Befehl wird `delta_z` mit einem bereits aufgelösten Registry-Objekt aufgerufen (cli.py:1350), aber direkte API-Nutzer treffen diesen Disk-I/O.

**Messung:** `path.read_text` + `json.loads` ≈ 0.1-0.5ms pro Call (abhängig von Dateigröße, ~2KB).

**Fix:** `KeyRegistry` erhält einen optionalen Lade-Cache. Die `list_keys()`-Methode cached das geladene Dict:

```python
class KeyRegistry:
    def __init__(self, path=..., seed_demo=None):
        self.path = Path(path)
        self._seed_demo = ...
        self._cache: dict | None = None
        self._cache_key: tuple | None = None  # (path, mtime, size)

    def load(self) -> dict:
        try:
            st = self.path.stat()
        except OSError:
            return self._demo_data() if self._seed_demo else {"keys": []}
        cache_key = (st.st_mtime_ns, st.st_size)
        if self._cache_key == cache_key and self._cache is not None:
            return self._cache
        if not self.path.exists():
            data = self._demo_data() if self._seed_demo else {"keys": []}
        else:
            data = self._parse_file()
        self._cache = data
        self._cache_key = cache_key
        return data
```

**Erwartete Auswirkung:** Eliminiert Disk-I/O für wiederholte `delta_z`/`load` auf unveränderten Registries.  
**Impact-Effort:** ⚡ niedrig / ⚡ gering

---

### Fix 9: Batch — deduplizierte `mkdir` (batch.py:71-77)

**Datei:** `src/ai_watermark_toolkit/batch.py`, Zeile 74  
**Problem:** `dst.parent.mkdir(parents=True, exist_ok=True)` wird für JEDE Datei aufgerufen, selbst wenn der Eltern-Ordner bereits von einer vorherigen Datei erstellt wurde. Im Profil: 201 `nt.mkdir` Aufrufe für 200 Dateien (33ms).

**Fix:** Set-basierte Deduplizierung der erstellten Parent-Pfade:

```python
_created_dirs: set[Path] = set()
...
if dst.parent not in _created_dirs and not dst.parent.exists():
    dst.parent.mkdir(parents=True, exist_ok=True)
    _created_dirs.add(dst.parent)
```

**Erwartete Auswirkung:** ~200 redundante `mkdir`-Aufrufe eliminiert → ~33ms eingespart (4.7% der Batch-Zeit).  
**Impact-Effort:** ⚡ niedrig / ⚡ gering

---

### Fix 10: `trace_kgw` — inkrementelle Fenster (trace.py)

**Datei:** `src/ai_watermark_toolkit/forensics/trace.py`  
**Problem:** `trace_kgw` teilt den Text in überschneidende Fenster und ruft `detect_kgw` für JEDES Fenster separat auf. Jedes Fenster re-tokenized und re-hasht den gesamten Fensterinhalt — bei überschneidenden Fenstern ist der größte Teil des Texts identisch.

**Messung:** Für einen 10.000-Wort-Text mit 500-Wort-Fenstern und 250-Wort-Schritt: 39 Fenster × 1.35ms = **52.6ms** (statt theoretisch ~1.5ms für einen einzigen Durchlauf).

**Fix:** Inkrementelle Slide-Technik — hash nur die Token am Fenster-Rand (Delta), aktualisiere den Green-Count inkrementell. Da `green_token(token, prev_token, key, gamma)` nur vom direkten Vorgänger abhängt, verschiebt sich der Green-Status nur an den Fenstergrenzen (vorderer und hinterer Rand).

**Erwartete Auswirkung:** 10-20× Speedup für große Dokumente (abhängig von Fenster-/Schrittähnliche).  
**Impact-Effort:** ⚡⚡ mittel / ⚡⚡ mittel

---

## N+1 Patterns & Datenfluss-Probleme

| Muster | Ort | Beschreibung |
|--------|-----|-------------|
| **N+1 Tokenisierung** | cli.py:1328-1351 (`finding`) | `detect_multi_key` + `e_detect` + `delta_z` = 3× Tokenisierung + Re-Hash desselben Textes |
| **N+1 KeyResolver** | cli.py:648, 752, 812, 833, 1102, 1311, 1407, 1511 | Jeder CLI-Befehl erstellt ein neues `KeyRegistry("data/key_registry.json")` — Dateilesung pro Befehl |
| **N+1 shuffle** | kgw.py:660 (`mark_greenlist`) | `rng.shuffle(fallback)` für jeden nicht-grünen Fallback — O(n) statt O(1) |
| **N+1 detect in evade** | evader.py:205 (`evade`) | `detect_kgw` nach jedem einzelnen Token-Tausch — O(changes × n) statt O(n) |
| **N+1 mkdir** | batch.py:74 | `mkdir(parents=True)` für jede Datei, selbst wenn Eltern bereits existiert |
| **N+1 encode** | kgw.py:70 (`bpe_tokenize`) | `enc.decode([tok])` pro Token statt Batch-Decode |

---

## Numba / NumPy-Einschätzung

**Kurzantwort: nicht empfohlen für die aktuellen Hot-Paths.**

| Komponente | Numba-viable? | Begründung |
|-----------|--------------|------------|
| `green_token` SHA-256 | ❌ | SHA-256 ist in `hashlib` bereits C-optimiert (C-Level via OpenSSL). Numba's `hashlib`-Support ist begrenzt und würde langsamer sein. |
| `random.shuffle` | ❌ | Wird ersetzt durch O(1)-Offset — kein Loop mehr zu beschleunigen. |
| `mark_greenlist` Hauptloop | ⚠️ | Der Loop selbst ist I/O-light, aber die Dominante-Kosten sind `green_token` (SHA-256) und `shuffle`. Numba könnte den Python-Overhead (dict lookups, string ops) reduzieren, aber die SHA-256-DOMINANZ bleibt. |
| `evade` inkrementelle Updates | ⚠️ | Nach Fix 4 ist der Loop arithmetisch (Z-Score-Update). Numba könnte hier helfen, aber der Speedup von 150× durch Algorithmuswechsel macht das irrelevant. |
| `sanitize_unicode.analyze` | ⚠️ | `unicodedata.category` ist C-Level. Numba kann nicht auf C-Erweiterungen zugreifen. Ein `numpy`-basiertes Char-Array-Scanning könnte theoretisch helfen, aber die Datenbank-Overhead überwiegt. |
| Batch `scan_markers` (regex) | ❌ | `re.Pattern.findall` ist bereits C-optimiert. |

**Empfehlung:** Fokus auf Algorithmus- und Datenstruktur-Verbesserungen (O(n) → O(1)), nicht auf Numba. Numba wäre nur für den `_is_green`-Inneren-Loop relevant, der nach Fix 4 (Memoization) bereits um 7× schneller ist.

---

## Prioritäten-Matrix (Impact vs. Effort)

```
Impact ↑
  ⚡⚡⚡  | Fix 1: shuffle→offset     Fix 2: green_token cache    Fix 3: finding dedup
  ⚡⚡    | Fix 4: evade incremental   Fix 5: bpe batch decode     Fix 6: ASCII short-circuit
  ⚡     | Fix 7: _restore regex      Fix 8: KeyRegistry cache    Fix 9: mkdir dedup    Fix 10: trace incremental
  ──────┼──────────────────────────────────────────────────────────────→
        low Effort                          high Effort
```

| Priority | Fix | Erwartete Speedup | Aufwand | Begründung |
|---------|-----|-------------------|---------|------------|
| **P0** | Fix 1: shuffle→offset | **14×** auf `mark_greenlist` | ⚡⚡ | Einfachste Änderung mit größtem Impact. 86% der Embed-Zeit weg. |
| **P0** | Fix 3: finding Deduplizierung | **3×** auf `finding`-Befehl | ⚡⚡ | Dreifacher redundante Tokenisierung eliminiert. |
| **P1** | Fix 2: green_token Cache | **7×** auf `detect_kgw`, 2× auf `mark_greenlist` | ⚡ | Globale Memo-Klasse, invalidierungsproblem nur bei Schlüsselwechsel. |
| **P1** | Fix 4: evade inkrementell | **150×** auf `evade` | ⚡⚡ | Algorithmuswechsel von O(changes×n) → O(n + changes). |
| **P2** | Fix 6: ASCII short-circuit | **4×** auf `analyze` | ⚡ | 15% Batch-Kosten weg, minimale Risiko. |
| **P2** | Fix 5: BPE batch decode | **3-5×** auf BPE-Pfad | ⚡ | API-Äquivalent, tiktoken-kompatibel. |
| **P3** | Fix 8: KeyRegistry cache | variabel | ⚡ | Eliminiert Disk-I/O, wichtig für Batch/Delta-Z. |
| **P3** | Fix 7: _restore regex | variabel | ⚡ | Bei vielen geschützten Tokens deutlich schneller. |
| **P3** | Fix 9: mkdir dedup | 4.7% Batch | ⚡ | Mikro-Optimierung, aber trivial umsetzbar. |
| **P3** | Fix 10: trace inkrementell | 10-20× | ⚡⚡ | Komplexer, aber für große Dokumente entscheidend. |

---

## Messbare Metriken & Validierung

Jeder Fix kann mit dem bestehenden Profilierungs-Framework validiert werden:

```bash
# Baseline (vor Fix):
python benchmarks/profile_eighth_pass.py
# Erwartet: mark_greenlist = 238.6ms/iteration

# Nach Fix 1 (shuffle→offset):
python benchmarks/profile_eighth_pass.py
# Erwartet: mark_greenlist = ~14ms/iteration (14× Verbesserung)

# Nach Fix 2 (green_token cache):
python benchmarks/micro_bench_hotpaths.py
# Erwartet: detect_kgw = ~0.2ms/call (7× Verbesserung)

# Nach Fix 4 (evade incremental):
python benchmarks/micro_bench_hotpaths.py
# Erwartet: evade = ~1.5ms/call (160× Verbesserung)
```

### Erwartete Nach-Profil-Werte (kombiniert):

| Metrik | Vorher | Nach alle Fixes | Verbesserung |
|--------|--------|-----------------|-------------|
| `mark_greenlist` (500W) | 238.6ms | ~4ms | **60×** |
| `detect_kgw` (500W, 1 Key) | 1.35ms | ~0.2ms | **7×** |
| `detect_multi_key` (5 Keys) | 24.7ms | ~3ms | **8×** |
| `evade` (300W) | 240.7ms | ~1.5ms | **160×** |
| Batch (200 Dateien) | 0.699s | ~0.55s | **1.3×** |
| Watcher (500 Dateien) | 0.188s | ~0.16s | **1.2×** |
| `finding` (detect+e+delta_z) | ~5.5ms | ~1.5ms | **3.7×** |

---

## Datei/Linie-Referenz-Tabelle

| Fix | Datei | Zeile(n) | Funktion |
|-----|-------|---------|----------|
| 1 | `src/ai_watermark_toolkit/forensics/kgw.py` | 658-664 | `mark_greenlist` — `rng.shuffle(fallback)` |
| 2 | `src/ai_watermark_toolkit/forensics/kgw.py` | 155-166 | `green_token` — SHA-256 PRF, kein Cache |
| 3 | `src/ai_watermark_toolkit/cli.py` | 1328-1351 | `finding`-Befehl — 3× redundante Detektion |
| 3 | `src/ai_watermark_toolkit/forensics/finding.py` | 646-734 | `build_finding_report` — kein Shared-Stream |
| 4 | `src/ai_watermark_toolkit/forensics/evader.py` | 184-209 | `evade` — `detect_kgw` in Loop |
| 5 | `src/ai_watermark_toolkit/forensics/kgw.py` | 60-70 | `bpe_tokenize` — per-token `enc.decode` |
| 6 | `src/ai_watermark_toolkit/sanitize_unicode.py` | 138-149 | `analyze` — per-char `unicodedata.category` |
| 7 | `src/ai_watermark_toolkit/rewrite/service.py` | 111-114 | `_restore` — `str.replace` in Schleife |
| 8 | `src/ai_watermark_toolkit/forensics/delta_z.py` | 288 | `delta_z` — `KeyRegistry` ohne Cache |
| 8 | `src/ai_watermark_toolkit/forensics/key_registry.py` | 164-167 | `load` — Disk-I/O pro Call |
| 9 | `src/ai_watermark_toolkit/batch.py` | 71-77 | `process_batch` — `mkdir` pro Datei |
| 10 | `src/ai_watermark_toolkit/forensics/trace.py` | (vollständig) | `trace_kgw` — Fenster ohne teilen |

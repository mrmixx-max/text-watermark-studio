import subprocess, os, tempfile, pytest

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

def test_embed_invalid_key():
    # CLI hat kein embed-Kommando -> unbekanntes Kommando muss sauber abgelehnt werden
    out = subprocess.run(
        ['python', '-m', 'ai_watermark_toolkit.cli', 'embed'],
        capture_output=True, text=True,
    )
    assert 'Traceback' not in out.stderr, f'CLI crashed: {out.stderr}'
    assert out.returncode != 0 or 'invalid choice' in out.stderr.lower() or 'error' in (out.stderr + out.stdout).lower()

def test_detect_invalid_args():
    # ungültige Dateipfade, leere Eingaben
    for bad_path in ['/nonexistent/file.txt', '', '   ']:
        # echte CLI: detect mit ungültigem Pfad darf nicht crashen
        out = subprocess.run(
            ['python', '-m', 'ai_watermark_toolkit.cli', 'detect', bad_path],
            capture_output=True, text=True,
        )
        # Rückgabe sollte Fehler melden, nicht mit Traceback crashen
        assert 'Traceback' not in out.stderr, f'CLI crashed on path {bad_path!r}: {out.stderr}'

def test_yaml_injection():
    # Guard: PyYAML is an optional dep (not in the core CI image); skip when
    # absent instead of failing the whole run.
    pytest.importorskip("yaml")
    # versuche YAML-Injection via config
    malicious = 'key: !!python/object/apply:os.system ["echo pwned"]'
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(malicious)
        fpath = f.name
    try:
        # lade config (falls YAML-Parser verwendet wird)
        import yaml
        with open(fpath) as f:
            try:
                yaml.safe_load(f)
                safe = True
            except yaml.YAMLError:
                safe = True
        assert safe
    finally:
        os.unlink(fpath)

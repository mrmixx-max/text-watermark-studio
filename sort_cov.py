import subprocess, sys

result = subprocess.run(
    [sys.executable, "-m", "coverage", "report"],
    capture_output=True, text=True
)
lines = result.stdout.strip().split("\n")
rows = []
for line in lines:
    parts = line.split()
    if len(parts) >= 7 and parts[-1] != "Cover":
        pct = parts[-1]
        if "%" in pct:
            pct_num = float(pct.replace("%", ""))
            rows.append((pct_num, line))
rows.sort(key=lambda x: x[0])
for pct, line in rows:
    print(f"{pct:6.2f}%  {line}")

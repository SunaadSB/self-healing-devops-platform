from pathlib import Path

FILES = [
    Path("ml/detect_anomalies.py"),
    Path("ml/detect_anomalies_v2.py"),
]

OLD = '''    df = df.dropna(subset=REQUIRED)
'''

NEW = '''    rows_before_filter = len(df)
    missing_by_column = df[REQUIRED].isna().sum()
    missing_required_rows = int(df[REQUIRED].isna().any(axis=1).sum())
    if missing_required_rows:
        print(
            f"WARNING: dropping {missing_required_rows} of {rows_before_filter} "
            "rows with missing required values. "
            f"Missing by column: {missing_by_column[missing_by_column > 0].to_dict()}"
        )
    df = df.dropna(subset=REQUIRED)
    print(f"Valid rows after required-field filtering: {len(df)} / {rows_before_filter}")
'''

originals = {}
for path in FILES:
    text = path.read_text(encoding="utf-8")
    if "rows_before_filter" in text:
        raise SystemExit(f"{path}: diagnostics already present; stopping.")
    if text.count(OLD) != 1:
        raise SystemExit(
            f"{path}: expected exactly one dropna line, found {text.count(OLD)}. "
            "No files changed."
        )
    originals[path] = text

updated = {path: text.replace(OLD, NEW, 1) for path, text in originals.items()}

for path, text in updated.items():
    temp = path.with_suffix(path.suffix + ".new")
    temp.write_text(text, encoding="utf-8", newline="")
    if "rows_before_filter" not in temp.read_text(encoding="utf-8"):
        temp.unlink(missing_ok=True)
        raise SystemExit(f"Verification failed for temporary file {temp}")

for path in FILES:
    temp = path.with_suffix(path.suffix + ".new")
    temp.replace(path)
    print(f"Updated and verified: {path}")

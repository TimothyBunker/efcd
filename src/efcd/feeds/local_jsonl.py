import json
import os


def load_local_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    bytes_size = os.path.getsize(path)
    return rows, bytes_size

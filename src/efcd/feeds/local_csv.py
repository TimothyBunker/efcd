import csv
import os


def load_local_csv(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    bytes_size = os.path.getsize(path)
    return rows, bytes_size

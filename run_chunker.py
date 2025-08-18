import json, csv, glob, os
from pathlib import Path
from markdown_chunker import build_chunk_index

CONFIG_PATH = "chunker.config.json"

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def resolve_inputs(globs_list):
    files = []
    for pattern in globs_list:
        files.extend(glob.glob(pattern, recursive=True))
    # only markdown files, unique, existing
    files = [f for f in files if f.lower().endswith(".md") and os.path.isfile(f)]
    # make paths deterministic
    return sorted(set(files))

def load_base_url_map(csv_path):
    if not csv_path or not os.path.exists(csv_path):
        return None
    mapping = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fn = row.get("filename", "").strip()
            url = row.get("url", "").strip()
            if fn and url:
                mapping[fn] = url
    return mapping or None

def main():
    cfg = load_config()
    input_files = resolve_inputs(cfg.get("input_globs", ["**/*.md"]))
    if not input_files:
        raise SystemExit("No Markdown files matched input_globs. Adjust chunker.config.json")

    base_map = load_base_url_map(cfg.get("base_url_map_file", ""))

    info = build_chunk_index(
        input_paths=input_files,
        max_tokens=int(cfg.get("max_tokens", 420)),
        min_tokens=int(cfg.get("min_tokens", 60)),
        overlap_sentences=int(cfg.get("overlap_sentences", 1)),
        cap_heading_level=cfg.get("cap_heading_level", 2),
        base_url_map=base_map,
        out_prefix=cfg.get("out_prefix", "aps_chunk_index")
    )

    print("Chunking complete:", info)

if __name__ == "__main__":
    main()

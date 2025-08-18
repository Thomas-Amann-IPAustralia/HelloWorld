from __future__ import annotations
import re, json, os, uuid
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import pandas as pd

HEADING_RE = re.compile(r'^(#{1,6})[ \t]+(.+?)\s*#*\s*$')
FENCE_RE = re.compile(r'^```')
LIST_RE = re.compile(r'^\s*(?:[-*+]|[0-9]{1,3}\.)\s+')
TABLE_RE = re.compile(r'^\s*\|.*\|\s*$')
QUOTE_RE = re.compile(r'^\s*>')
HR_RE = re.compile(r'^\s*([-*_]\s*){3,}\s*$')
BLANK_RE = re.compile(r'^\s*$')

def approx_tokens(text: str) -> int:
    words = len(re.findall(r"\S+", text))
    return max(1, int(round(words * 1.33)))

def sentence_split(text: str) -> List[str]:
    parts = re.split(r'(?<=[\.\?\!\:])\s+(?=[A-Z0-9“"(\[])', text.strip())
    return [p for p in parts if p.strip()]

def slugify(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r'[^\w\s-]', '', t)
    t = re.sub(r'[\s_-]+', '-', t).strip('-')
    return t

@dataclass
class Chunk:
    chunk_id: str
    file_name: str
    source_path: str
    heading_path: List[str]
    start_line: int
    end_line: int
    char_start: int
    char_end: int
    tokens: int
    text: str
    anchor_fragment: Optional[str] = None
    source_url: Optional[str] = None
    jump_url: Optional[str] = None

def parse_markdown_blocks(md_text: str) -> List[Tuple[int, int, str, List[str]]]:
    lines = md_text.splitlines()
    n = len(lines)
    blocks = []
    in_code = False
    cur_block_lines: List[str] = []
    cur_block_start = 0
    current_heading_path: List[str] = []
    pending_type = None

    def flush_block(end_idx: int, hpath: List[str]):
        nonlocal cur_block_lines, cur_block_start, pending_type
        if cur_block_lines:
            blocks.append((cur_block_start+1, end_idx+1, "\n".join(cur_block_lines).rstrip(), list(hpath)))
            cur_block_lines = []
            pending_type = None

    for i, line in enumerate(lines):
        if FENCE_RE.match(line):
            if not in_code:
                flush_block(i-1, current_heading_path)
                in_code = True
                cur_block_start = i
                cur_block_lines = [line]
                pending_type = 'code'
            else:
                cur_block_lines.append(line)
                flush_block(i, current_heading_path)
                in_code = False
            continue

        if in_code:
            cur_block_lines.append(line)
            continue

        m = HEADING_RE.match(line)
        if m:
            flush_block(i-1, current_heading_path)
            level = len(m.group(1))
            heading_text = m.group(2).strip()
            current_heading_path = current_heading_path[:level-1] + [heading_text]
            blocks.append((i+1, i+1, line.rstrip(), list(current_heading_path)))
            continue

        if HR_RE.match(line):
            flush_block(i-1, current_heading_path)
            blocks.append((i+1, i+1, line.rstrip(), list(current_heading_path)))
            continue

        if BLANK_RE.match(line):
            flush_block(i-1, current_heading_path)
            continue

        this_type = (
            'table' if TABLE_RE.match(line) else
            'list' if LIST_RE.match(line) else
            'quote' if QUOTE_RE.match(line) else
            'para'
        )

        if pending_type is None:
            pending_type = this_type
            cur_block_start = i
            cur_block_lines = [line]
        elif this_type == pending_type:
            cur_block_lines.append(line)
        else:
            flush_block(i-1, current_heading_path)
            pending_type = this_type
            cur_block_start = i
            cur_block_lines = [line]

    flush_block(n-1, current_heading_path)
    return blocks

def make_anchor_fragment(heading_path: List[str], cap_heading_level: int) -> Optional[str]:
    if not heading_path:
        return None
    depth = min(len(heading_path), cap_heading_level)
    parts = [slugify(h) for h in heading_path[:depth] if h.strip()]
    if not parts:
        parts = [slugify(heading_path[-1])]
    return "#" + "/".join(parts)

def pack_blocks_into_chunks(blocks: List[Tuple[int,int,str,List[str]]],
                            file_name: str,
                            source_path: str,
                            max_tokens: int = 500,
                            min_tokens: int = 80,
                            overlap_sentences: int = 1,
                            cap_heading_level: Optional[int] = 2,
                            base_url_map: Optional[Dict[str, str]] = None) -> List[Chunk]:
    chunks: List[Chunk] = []
    buf_lines: List[str] = []
    buf_start_line = None
    buf_heading: List[str] = []
    char_pos = 0

    def section_key(hpath: List[str]) -> Tuple[str, ...]:
        if not hpath or cap_heading_level is None:
            return tuple(hpath or [])
        return tuple(hpath[:cap_heading_level])

    def finalize_buffer(end_line: int, hpath: List[str]):
        nonlocal buf_lines, buf_start_line, buf_heading, char_pos
        if not buf_lines:
            return
        text = "\n".join(buf_lines).strip()
        if not text:
            buf_lines, buf_start_line = [], None
            return
        toks = approx_tokens(text)
        if toks < min_tokens and chunks:
            prev = chunks[-1]
            if section_key(prev.heading_path) == section_key(hpath) and prev.tokens + toks <= max_tokens:
                prev.text = prev.text.rstrip() + "\n\n" + text
                prev.tokens = approx_tokens(prev.text)
                prev.end_line = end_line
                prev.char_end += len(text) + 2
                buf_lines, buf_start_line = [], None
                return

        frag = make_anchor_fragment(hpath, cap_heading_level or len(hpath))
        src_url = (base_url_map or {}).get(file_name) if base_url_map else None
        jump = (src_url + frag) if (src_url and frag) else None

        c = Chunk(
            chunk_id=str(uuid.uuid4()),
            file_name=file_name,
            source_path=source_path,
            heading_path=list(hpath),
            start_line=buf_start_line or 1,
            end_line=end_line,
            char_start=char_pos,
            char_end=char_pos + len(text),
            tokens=toks,
            text=text,
            anchor_fragment=frag,
            source_url=src_url,
            jump_url=jump
        )
        char_pos += len(text) + 2
        chunks.append(c)
        buf_lines, buf_start_line = [], None

    last_sec_key: Optional[Tuple[str, ...]] = None

    for (sline, eline, block_text, hpath) in blocks:
        blk_sec_key = section_key(hpath)

        if last_sec_key is not None and blk_sec_key != last_sec_key:
            finalize_buffer(eline-1, buf_heading if buf_heading else hpath)
            buf_lines, buf_start_line = [], None

        last_sec_key = blk_sec_key

        block_tokens = approx_tokens(block_text)
        if not buf_lines:
            buf_start_line = sline
            buf_heading = hpath

        current_tokens = approx_tokens("\n".join(buf_lines)) if buf_lines else 0
        if current_tokens + block_tokens <= max_tokens:
            buf_lines.append(block_text)
            continue

        if buf_lines:
            finalize_buffer(eline - 1, buf_heading)

        sentences = sentence_split(block_text)
        sent_buf: List[str] = []
        sent_start_line = sline
        for idx, sent in enumerate(sentences):
            sent_tokens = approx_tokens(sent)
            cur_toks = approx_tokens(" ".join(sent_buf)) if sent_buf else 0
            if cur_toks + sent_tokens <= max_tokens:
                sent_buf.append(sent)
                continue

            c_text = " ".join(sent_buf).strip()
            if c_text:
                frag = make_anchor_fragment(hpath, cap_heading_level or len(hpath))
                src_url = (base_url_map or {}).get(file_name) if base_url_map else None
                jump = (src_url + frag) if (src_url and frag) else None
                chunks.append(Chunk(
                    chunk_id=str(uuid.uuid4()),
                    file_name=file_name,
                    source_path=source_path,
                    heading_path=list(hpath),
                    start_line=sent_start_line,
                    end_line=eline,
                    char_start=0,
                    char_end=0,
                    tokens=approx_tokens(c_text),
                    text=c_text,
                    anchor_fragment=frag,
                    source_url=src_url,
                    jump_url=jump
                ))
            if overlap_sentences > 0 and idx > 0:
                overlap = sentences[max(0, idx-overlap_sentences):idx]
                sent_buf = overlap + [sent]
            else:
                sent_buf = [sent]
            sent_start_line = sline

        if sent_buf:
            c_text = " ".join(sent_buf).strip()
            frag = make_anchor_fragment(hpath, cap_heading_level or len(hpath))
            src_url = (base_url_map or {}).get(file_name) if base_url_map else None
            jump = (src_url + frag) if (src_url and frag) else None
            chunks.append(Chunk(
                chunk_id=str(uuid.uuid4()),
                file_name=file_name,
                source_path=source_path,
                heading_path=list(hpath),
                start_line=sent_start_line,
                end_line=eline,
                char_start=0,
                char_end=0,
                tokens=approx_tokens(c_text),
                text=c_text,
                anchor_fragment=frag,
                source_url=src_url,
                jump_url=jump
            ))

        buf_lines, buf_start_line = [], None
        buf_heading = hpath

    if buf_lines:
        finalize_buffer(blocks[-1][1], buf_heading)

    return chunks

def chunk_markdown_file(path: str,
                        max_tokens: int = 500,
                        min_tokens: int = 80,
                        overlap_sentences: int = 1,
                        cap_heading_level: Optional[int] = 2,
                        base_url_map: Optional[Dict[str,str]] = None) -> List[Dict[str, Any]]:
    text = Path(path).read_text(encoding="utf-8")
    blocks = parse_markdown_blocks(text)
    chunks = pack_blocks_into_chunks(
        blocks,
        file_name=os.path.basename(path),
        source_path=path,
        max_tokens=max_tokens,
        min_tokens=min_tokens,
        overlap_sentences=overlap_sentences,
        cap_heading_level=cap_heading_level,
        base_url_map=base_url_map
    )
    return [asdict(c) for c in chunks]

def save_jsonl(records: List[Dict[str, Any]], out_path: str):
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def build_chunk_index(input_paths: List[str],
                      max_tokens: int = 500,
                      min_tokens: int = 80,
                      overlap_sentences: int = 1,
                      cap_heading_level: Optional[int] = 2,
                      base_url_map: Optional[Dict[str,str]] = None,
                      out_prefix: str = "aps_chunk_index") -> Dict[str, Any]:
    all_chunks: List[Dict[str, Any]] = []
    for p in input_paths:
        chunks = chunk_markdown_file(
            p,
            max_tokens=max_tokens,
            min_tokens=min_tokens,
            overlap_sentences=overlap_sentences,
            cap_heading_level=cap_heading_level,
            base_url_map=base_url_map
        )
        all_chunks.extend(chunks)

    jsonl_path = f"{out_prefix}.jsonl"
    csv_path = f"{out_prefix}.csv"
    save_jsonl([asdict(c) if isinstance(c, Chunk) else c for c in all_chunks], jsonl_path)

    import pandas as pd
    df = pd.DataFrame(all_chunks)
    cols = ["chunk_id","file_name","heading_path","start_line","end_line","tokens","anchor_fragment","jump_url","text","source_path","char_start","char_end","source_url"]
    df = df[cols]
    df.to_csv(csv_path, index=False, encoding="utf-8")
    return {"jsonl_path": jsonl_path, "csv_path": csv_path, "count": len(all_chunks)}

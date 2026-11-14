#!/usr/bin/env python3
"""Retain complete requirement responses before extracting criteria; no network I/O.

requirements.py RESPONSE --source URL --retrieved-at ISO --revision REVISION
    --coverage complete|partial|unavailable --output SNAPSHOT.json

The output is created exclusively, never overwritten. Keep it beside raw evidence,
then include its object in ticketEvidence.source_snapshots before extraction.
"""
import argparse
import hashlib
import json
from pathlib import Path


def snapshot(body, source, retrieved_at, revision, coverage):
    return dict(source=source, retrieved_at=retrieved_at, revision=revision,
                coverage=coverage, sha256=hashlib.sha256(body.encode()).hexdigest(), body=body)


def requirement_gaps(ticket):
    """Check retained source provenance and matrix consistency, not completeness."""
    gaps = []
    if ticket.get("tickets") and not ticket.get("requirements"):
        gaps.append("requirements-source-not-collected")
    snapshots = {s.get("sha256"): s for s in ticket.get("source_snapshots", [])}
    for saved in snapshots.values():
        if (not all(saved.get(k) for k in ("source", "retrieved_at", "revision"))
                or saved.get("coverage") != "complete" or not isinstance(saved.get("body"), str)
                or hashlib.sha256(saved["body"].encode()).hexdigest() != saved.get("sha256")):
            gaps.append("requirements-snapshot-unavailable:" + str(saved.get("source", "unknown")))
    for source in ticket.get("requirements", []):
        identity = source.get("source", "unknown")
        if not all(source.get(k) for k in ("source", "retrieved_at")) or "acceptance_text" not in source:
            gaps.append("requirements-source-unavailable")
            continue
        saved = snapshots.get(source.get("snapshot_sha256"))
        if not saved:
            gaps.append("requirements-original-source-not-retained:" + identity)
        else:
            try:
                body = saved["body"]
                if source.get("source_path"):
                    body = json.loads(body)
                    for key in source["source_path"]:
                        body = body[key]
                if not isinstance(body, str):
                    raise ValueError("source path must select text")
                start, end = source.get("section", [0, len(body)])
                if not (type(start) is int and type(end) is int and 0 <= start <= end <= len(body)):
                    raise ValueError("invalid section offsets")
                if (saved["source"] != identity or saved["retrieved_at"] != source["retrieved_at"]
                        or source["acceptance_text"] != body[start:end]):
                    raise ValueError("acceptance text differs from retained section")
            except (ValueError, KeyError, TypeError, IndexError):
                gaps.append("requirements-section-mismatch:" + identity)
        criteria = source.get("criteria", [])
        text = source["acceptance_text"].strip()
        if text and not criteria:
            gaps.append("requirements-extraction-mismatch:" + identity)
        mapped = {row.get("criterion_id") for row in source.get("matrix", [])}
        if any(c["id"] not in mapped or c["quote"] not in text for c in criteria):
            gaps.append("requirements-matrix-incomplete:" + identity)
    return sorted(set(gaps))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("response", type=Path)
    parser.add_argument("--source", required=True)
    parser.add_argument("--retrieved-at", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--coverage", required=True, choices=("complete", "partial", "unavailable"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # read_bytes preserves CRLF and the exact response bytes in the digest.
    body = args.response.read_bytes().decode("utf-8")
    saved = snapshot(body, args.source, args.retrieved_at, args.revision, args.coverage)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(saved, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(saved["sha256"])


if __name__ == "__main__":
    main()

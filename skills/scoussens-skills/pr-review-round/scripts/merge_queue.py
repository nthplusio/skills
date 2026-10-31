"""Read actual queue membership; CLEAN and auto-merge are not membership."""
import json
import subprocess


def queue_state(node_id, head):
    if not node_id or not head:
        return "unknown"
    result = subprocess.run([
        "gh", "api", "graphql", "-f", "query="
        "query($id: ID!) { node(id: $id) { ... on PullRequest { "
        "headRefOid mergeQueueEntry { id } } } }",
        "-f", f"id={node_id}",
    ], capture_output=True, text=True)
    if result.returncode:
        return "unknown"
    try:
        data = json.loads(result.stdout)
        node = data["data"]["node"]
        if data.get("errors") or node["headRefOid"] != head:
            return "unknown"
        entry = node["mergeQueueEntry"]
        if entry is None:
            return "not_queued"
        return "queued" if entry.get("id") else "unknown"
    except (ValueError, KeyError, TypeError, AttributeError):
        return "unknown"

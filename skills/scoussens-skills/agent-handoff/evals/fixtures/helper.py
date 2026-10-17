import json
from pathlib import Path

result = json.loads(Path(__file__).with_name("input.json").read_text())["answer"]

from pathlib import Path
import runpy

helper = runpy.run_path(str(Path(__file__).with_name("helper.py")))
print(helper["result"])

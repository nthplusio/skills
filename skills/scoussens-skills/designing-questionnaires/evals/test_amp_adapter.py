import shutil
import subprocess
import unittest
from pathlib import Path


class AmpAdapterTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("bun"), "Amp adapter contract test needs Bun; no live Amp test implied")
    def test_delivery_contract(self):
        subprocess.run(["bun", str(Path(__file__).with_name("amp-adapter.mjs"))], check=True)

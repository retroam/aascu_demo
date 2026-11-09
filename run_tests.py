"""Run demo tests on a disposable baseline, independent of the active dashboard dataset."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import foundations
import pdp_model
import yaml


def main():
    """Build an isolated starter fixture and run both test suites against it."""
    with tempfile.TemporaryDirectory(prefix="pdp-demo-tests-") as folder:
        root = Path(folder)
        config = yaml.safe_load(pdp_model.PIPELINE_CONFIG.read_text())
        config.update(logs_dir=str(root / "logs"), staging_dir=str(root / "staging"))
        pdp_model.PIPELINE_CONFIG = root / "pipeline.yaml"
        pdp_model.PIPELINE_CONFIG.write_text(yaml.safe_dump(config))
        baseline = root / "pdp.sqlite"
        pdp_model.run_load(f"sqlite:///{baseline}", pdp_model.new_run_id(), tables_dir=root / "tables")
        env = {**os.environ, "PDP_DEMO_DATABASE": str(baseline)}
        subprocess.run([sys.executable, "-m", "unittest", "discover", "-p", "test_*.py", "-v"], env=env, check=True)
        subprocess.run(["node", "--test", *sorted(str(p) for p in Path('.').glob('test_*.mjs'))], check=True)


if __name__ == "__main__":
    main()

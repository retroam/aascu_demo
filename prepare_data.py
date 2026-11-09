"""Build a disposable demo database with the starter's public loader API."""
from foundations import DATABASE
from pdp_model import new_run_id, run_load


if __name__ == "__main__":
    DATABASE.parent.mkdir(exist_ok=True)
    summary = run_load(f"sqlite:///{DATABASE}", new_run_id(), tables_dir=DATABASE.parent / "tables")
    print(summary)

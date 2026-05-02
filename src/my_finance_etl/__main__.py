"""Main entry point for the My Finance ETL package."""

import sys
from pathlib import Path

# Add the project root to sys.path so imports work
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def main():
    """Run the Kedro project."""
    try:
        from kedro.framework.project import configure_project
        from kedro.framework.session import KedroSession
    except ImportError as e:
        print(f"Error: Kedro is not available. Please install dependencies: {e}")
        sys.exit(1)

    try:
        configure_project("my_finance_etl")

        with KedroSession.create(project_path=".") as session:
            session.run()

    except Exception as e:
        print(f"Error running Kedro project: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
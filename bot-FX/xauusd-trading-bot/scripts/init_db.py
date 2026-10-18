"""Creates the configured schema without starting the broker runtime."""

import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import get_app_settings
from app.database import Database


def main() -> None:
    load_dotenv()
    database = Database(get_app_settings().database_url)
    database.create_schema()
    print("Database schema is ready")


if __name__ == "__main__":
    main()

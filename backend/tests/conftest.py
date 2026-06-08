import os
import sys
import tempfile
from pathlib import Path

TEST_ROOT = Path(tempfile.mkdtemp(prefix="ldm-tests-"))
os.environ.setdefault("LDM_DATABASE_URL", f"sqlite+aiosqlite:///{(TEST_ROOT / 'test.db').as_posix()}")
os.environ.setdefault("LDM_DATA_ROOT", str(TEST_ROOT / "data"))
os.environ.setdefault("LDM_CODEX_SESSIONS_DIR", str(TEST_ROOT / "codex_sessions"))

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv
from pathlib import Path
import os

_backend_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(_backend_dir / ".env")

# Resolve GOOGLE_APPLICATION_CREDENTIALS relative to backend/ if not absolute
_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if _creds and not Path(_creds).is_absolute():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(_backend_dir / _creds)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
# Server-side writes (e.g. patient_raw) use this when present — it bypasses RLS.
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

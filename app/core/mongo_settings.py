import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "knowlayer")

USERS_COLLECTION = os.getenv("USERS_COLLECTION", "users")
ROLES_COLLECTION = os.getenv("ROLES_COLLECTION", "roles")
DOCUMENTS_COLLECTION = os.getenv("DOCUMENTS_COLLECTION", "documents")
COUNTERS_COLLECTION = os.getenv("COUNTERS_COLLECTION", "counters")

EMPLOYEE_ID_PREFIX = os.getenv("EMPLOYEE_ID_PREFIX", "MSS")
EMPLOYEE_ID_MIN_DIGITS = int(os.getenv("EMPLOYEE_ID_MIN_DIGITS", "3"))
DOCUMENT_ID_PREFIX = os.getenv("DOCUMENT_ID_PREFIX", "DOC")
DOCUMENT_ID_MIN_DIGITS = int(os.getenv("DOCUMENT_ID_MIN_DIGITS", "3"))

EMAIL_DOMAIN = os.getenv("EMAIL_DOMAIN", "mclarensv.com")

DEFAULT_ROLES = {
    "manager": "Manager",
    "tester": "Tester",
    "solution_architect": "Solution Architect",
    "developer": "Developer",
}

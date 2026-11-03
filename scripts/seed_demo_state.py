"""KnowLayer V3 Enterprise - Demo Database & Vector Store Provisioning Script.

Seeds a complete, clean, demonstration-ready state matching E2E Acts 1-7:
1. Cleans stale database tables, orphan files in input/, and caches.
2. Resets Chroma vector collection ('Company_Docs').
3. Seeds Departments: Human Resources & Engineering.
4. Seeds Demo Users with uniform password 'Password123!':
   - admin (System Admin)
   - sarah.admin (Sarah Chen - Administrator)
   - roy.hr (Roy Miller - Manager, Human Resources)
   - david.hr (David Kim - Developer, Human Resources)
   - marcus.eng (Marcus Vance - Manager, Engineering)
   - elena.dev (Elena Rostova - Developer, Engineering)
5. Seeds Projects & Memberships:
   - Project Titan (Manager: Marcus Vance; Members: Roy Miller, Elena Rostova)
   - Project Apollo (Manager: Elena Rostova; Members: David Kim)
6. Ingests Synthetic Documents into Chroma & SQLite (all Status: Active):
   - timesheet_policy.md (General Knowledge Base / Unassigned)
   - titan_architecture.md (Project Titan)
   - apollo_blueprint.md (Project Apollo)
"""

import base64
from functools import partial
import os
from pathlib import Path
import shutil
import sqlite3
import sys

# Ensure repository root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv

load_dotenv(BASE_DIR / ".env")

from app.api.dependencies import get_business_id_generator, get_document_processor
from app.core.settings import COLLECTION_NAME, DATABASE_URL, DOCUMENTS_DIR
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.infrastructure.authentication.password_hasher import PasswordHasher
from app.infrastructure.ingestion.provisioner import provision_document
from app.infrastructure.persistence.factory import create_unit_of_work, get_session_factory, initialize_persistence
from app.infrastructure.vector.chroma_client import ChromaVectorStore
from app.use_cases.organization.department_membership import DepartmentMembershipService
from app.use_cases.organization.document_management import DocumentManagementService
from app.use_cases.organization.membership_management import MembershipManagementService
from app.use_cases.organization.project_management import ProjectManagementService
from app.use_cases.organization.user_management import UserManagementService

ADMIN_UID = "admin"
DEFAULT_DEMO_PASSWORD = "Password123!"


def reset_sqlite():
    """Wipe stale rows from SQLite database."""
    db_file = BASE_DIR / "instance" / "knowlayer.db"
    db_file.parent.mkdir(parents=True, exist_ok=True)
    if not db_file.exists():
        print(f"[SQL] Database file not present at {db_file}, will be initialized fresh.")
        return

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    tables = [
        "conversation_logs",
        "authentication_audit_events",
        "document_access",
        "user_projects",
        "department_members",
        "documents",
        "projects",
        "users",
        "departments",
        "role_permissions",
        "permissions",
        "roles",
    ]

    for table in tables:
        try:
            cur.execute(f"DELETE FROM {table}")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()
    print("[SQL] Cleared existing tables in knowlayer.db.")


def reset_chroma():
    """Wipe and recreate empty Chroma collection."""
    persist_dir = str(BASE_DIR / ".chroma")
    store = ChromaVectorStore(collection_name=COLLECTION_NAME, persist_directory=persist_dir)
    try:
        store.client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    store.client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    print(f"[Chroma] Re-initialized empty collection '{COLLECTION_NAME}' (0 vectors).")


def clean_input_and_caches():
    """Clean orphan project directories in input/ and local cache files."""
    input_dir = BASE_DIR / "input"
    if input_dir.exists():
        for item in input_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            elif item.is_file() and not item.name.endswith(".pdf"):
                item.unlink()
    input_dir.mkdir(parents=True, exist_ok=True)
    print("[Storage] Reset input/ storage directory.")

    cache_files = [
        BASE_DIR / "data" / "response_cache.json",
        BASE_DIR / "data" / "faqs_cache.json",
        BASE_DIR / "cache" / "semantic_cache.json",
    ]
    for c in cache_files:
        if c.exists():
            try:
                c.unlink()
            except OSError:
                pass
    print("[Cache] Reset response and FAQ cache files.")


def main():
    print("\n" + "=" * 70)
    print("KnowLayer V3 Enterprise - Demo Database & Vector Seeder")
    print("=" * 70)

    # 1. Reset storage & database
    reset_sqlite()
    reset_chroma()
    clean_input_and_caches()

    # 2. Initialize persistence & bootstrap admin
    session_factory = get_session_factory()
    initialize_persistence(lambda: session_factory)
    uow_factory = create_unit_of_work
    hasher = PasswordHasher()
    id_gen = get_business_id_generator()

    # Ensure admin has DEFAULT_DEMO_PASSWORD
    with uow_factory() as uow:
        admin_user = uow.users.get_by_uid(ADMIN_UID)
        if admin_user:
            new_hash = hasher.hash(DEFAULT_DEMO_PASSWORD)
            admin_user.password_representation = new_hash
            admin_user.password_hash = new_hash
            admin_user.must_change_password = False
            uow.users.save(admin_user)
            uow.commit()

    # 3. Instantiate Domain Services
    users_svc = UserManagementService(uow_factory, hasher, business_id_generator=id_gen)
    projects_svc = ProjectManagementService(uow_factory, business_id_generator=id_gen)
    dept_members_svc = DepartmentMembershipService(uow_factory)
    proj_members_svc = MembershipManagementService(uow_factory)

    # Ingestion handler for DocumentManagementService
    processor = get_document_processor()
    ingest_handler = partial(provision_document, processor=processor)
    docs_svc = DocumentManagementService(
        unit_of_work_factory=uow_factory,
        ingestion_handler=ingest_handler,
        business_id_generator=id_gen,
    )

    # 4. Seed Departments
    print("\n-> Seeding Departments...")
    hr_dept = users_svc.create_department(
        actor_uid=ADMIN_UID,
        department_name="Human Resources",
        description="Recruitment, onboarding, employee relations, and policy compliance.",
        default_billable="non-billable",
    )
    print(f"   [+] {hr_dept.department_id}: Human Resources (non-billable)")

    eng_dept = users_svc.create_department(
        actor_uid=ADMIN_UID,
        department_name="Engineering",
        description="Platform engineering, telemetry distributed systems, and core apps.",
        default_billable="billable",
    )
    print(f"   [+] {eng_dept.department_id}: Engineering (billable)")

    # 5. Seed Users
    print("\n-> Seeding Users (Password: Password123!)...")
    user_specs = [
        ("sarah.admin", "Sarah Chen", "sarah@nexora.com", "Admin", eng_dept.department_id, "Platform Administrator"),
        ("roy.hr", "Roy Miller", "roy@nexora.com", "Manager", hr_dept.department_id, "HR Manager"),
        ("david.hr", "David Kim", "david@nexora.com", "Developer", hr_dept.department_id, "HR Operations Developer"),
        ("marcus.eng", "Marcus Vance", "marcus@nexora.com", "Manager", eng_dept.department_id, "Engineering Lead"),
        ("elena.dev", "Elena Rostova", "elena@nexora.com", "Developer", eng_dept.department_id, "Senior Backend Developer"),
    ]

    users = {}
    for username, name, email, role, dept_id, job_title in user_specs:
        user = users_svc.create_user(
            actor_uid=ADMIN_UID,
            uid=username,
            name=name,
            email=email,
            role=role,
            department_id=dept_id,
            username=username,
            initial_password=DEFAULT_DEMO_PASSWORD,
            first_name=name.split()[0],
            last_name=name.split()[-1],
        )
        users[username] = user
        # Assign department membership
        dept_billable = "non-billable" if dept_id == hr_dept.department_id else "billable"
        dept_members_svc.assign(ADMIN_UID, user.uid, dept_id, billable_status=dept_billable, membership_role=role)
        print(f"   [+] {user.employee_id}: {name} ({username}) | Role: {role} | Dept: {dept_id}")

    # 6. Seed Projects
    print("\n-> Seeding Projects...")
    titan = projects_svc.create_project(
        actor_uid=ADMIN_UID,
        project_name="Project Titan",
        department_id=eng_dept.department_id,
        manager_uid=users["marcus.eng"].uid,
        description="High-throughput telemetry and distributed event streaming engine.",
    )
    print(f"   [+] {titan.project_id}: Project Titan (Manager: Marcus Vance)")

    apollo = projects_svc.create_project(
        actor_uid=ADMIN_UID,
        project_name="Project Apollo",
        department_id=eng_dept.department_id,
        manager_uid=users["elena.dev"].uid,
        description="Autonomous telemetry exploration payload and edge analytics.",
    )
    print(f"   [+] {apollo.project_id}: Project Apollo (Manager: Elena Rostova)")

    # 7. Seed Project Memberships
    print("\n-> Seeding Project Memberships...")
    # Roy Miller has cross-department membership in Project Titan
    proj_members_svc.assign(ADMIN_UID, users["roy.hr"].uid, titan.project_id, membership_role="Member")
    print(f"   [+] Roy Miller -> Project Titan (Cross-department grant)")

    # Elena Rostova is member of Project Titan
    proj_members_svc.assign(ADMIN_UID, users["elena.dev"].uid, titan.project_id, membership_role="Developer")
    print(f"   [+] Elena Rostova -> Project Titan (Member)")

    # David Kim is member of Project Apollo
    proj_members_svc.assign(ADMIN_UID, users["david.hr"].uid, apollo.project_id, membership_role="Developer")
    print(f"   [+] David Kim -> Project Apollo (Member)")

    # 8. Ingest Documents into Chroma & SQLite
    print("\n-> Ingesting Synthetic Documents into Chroma & SQLite...")
    docs_to_ingest = [
        (
            "timesheet_policy.md",
            BASE_DIR / "tests" / "fixtures" / "synthetic_data" / "timesheet_policy.md",
            None,
            "Official weekly timesheet submission, client billing attribution, and approval protocol.",
        ),
        (
            "titan_architecture.md",
            BASE_DIR / "tests" / "fixtures" / "synthetic_data" / "titan_architecture.md",
            titan.project_id,
            "Enterprise real-time analytics & microservices blueprint for Project Titan.",
        ),
        (
            "apollo_blueprint.md",
            BASE_DIR / "tests" / "fixtures" / "synthetic_data" / "apollo_blueprint.md",
            apollo.project_id,
            "Technical architecture and deployment blueprint for Project Apollo.",
        ),
    ]

    for doc_name, file_path, project_id, description in docs_to_ingest:
        assert file_path.exists(), f"Source file {file_path} not found"
        raw_bytes = file_path.read_bytes()
        content_b64 = base64.b64encode(raw_bytes).decode("utf-8")

        scope_lbl = f"Project '{project_id}'" if project_id else "General Knowledge Base (Unassigned)"
        print(f"   - Ingesting '{doc_name}' into {scope_lbl}...", flush=True)

        doc = docs_svc.register_document(
            principal=AuthenticatedPrincipal(ADMIN_UID),
            document_name=doc_name,
            original_filename=doc_name,
            source_path=str(file_path),
            content=content_b64,
            file_type="md",
            description=description,
            project_id=project_id,
            defer_ingestion=False,  # Synchronous extraction, chunking, and embedding
        )
        print(f"     [OK] Document {doc.document_id} ('{doc_name}') ingested successfully (Status: Active).")

    # 9. Print Demonstration Summary Table
    print("\n" + "=" * 70)
    print("DEMO ENVIRONMENT SEEDING COMPLETE")
    print("=" * 70)
    print("""
### Ready-to-Use Accounts (All passwords: Password123!)

| Username     | Password      | Name          | Role      | Department        | Scope & Purpose |
|--------------|---------------|---------------|-----------|-------------------|-----------------|
| admin        | Password123!  | Administrator | Admin     | Administration    | Superadmin      |
| sarah.admin  | Password123!  | Sarah Chen    | Admin     | Engineering       | Delegated Admin |
| roy.hr       | Password123!  | Roy Miller    | Manager   | Human Resources   | HR Lead, Titan  |
| david.hr     | Password123!  | David Kim     | Developer | Human Resources   | HR Dev, Apollo  |
| marcus.eng   | Password123!  | Marcus Vance  | Manager   | Engineering       | Titan Manager   |
| elena.dev    | Password123!  | Elena Rostova | Developer | Engineering       | Apollo Manager  |

### Projects Configured:
- **Project Titan** (`{titan_id}`): Managed by Marcus Vance. Members: Roy Miller, Elena Rostova.
- **Project Apollo** (`{apollo_id}`): Managed by Elena Rostova. Members: David Kim.

### Documents Indexed in Chroma:
- `timesheet_policy.md` (General KB - Unassigned)
- `titan_architecture.md` (Project Titan)
- `apollo_blueprint.md` (Project Apollo)
""".format(titan_id=titan.project_id, apollo_id=apollo.project_id))


if __name__ == "__main__":
    main()

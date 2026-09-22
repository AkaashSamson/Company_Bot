# Roshan — Requirement-to-File Change Plan (v3)

## Original requirement list (source of truth)

- **A user can see only other people in his department as of now, not all the people in the company.**
- **Logged out after refresh.**
- **Project page has some error message on Streamlit, need to fix it.**
- **Admin/Manager not allowed to delete, modify, or edit documents/users once they are created.**
- **UID is not auto-created.**
- **Dept ID not auto-created.**
- **Document ID can be text, no.**
- **RegisterDocument (metadata only) not required.**
- **Once a document is uploaded as unassigned, admin should be able to change access.**

> Decision (confirmed): requirement 4 means **admin/manager must be able to edit and delete users and documents after they are created**. The plan below therefore *adds/hardens* update + delete paths.

---

## 1. Company-wide people directory (see all people in the company)

**Why:** `OrganizationExplorerService.get_organization` (`app\use_cases\organization\organization_explorer.py:45-138`) only surfaces projects/members that fall inside the caller's access scope, so the explorer effectively shows only colleagues in the caller's own department. There is currently no organization-wide people listing.

**Files to change:**
- `app\api\schemas\explorer.py` — add a `PeopleDirectoryEntry` model (uid, name, email, role, department_id, department_name) and a `people` field on `OrganizationExplorerResponse`. Reason: the API contract must carry the new directory, and the Streamlit page renders only what this schema allows.
- `app\use_cases\organization\organization_explorer.py` — inside `get_organization`, build the `people` list from all *active* users in `uow.users.list()` joined to department names (email/role/department included; content/storage stays hidden). Reason: this is the single, authorization-unaware-but-readonly place that already resolves departments and people; adding the directory here keeps one source of truth for explorer output.
- `streamlit_app\services\explorer_api.py` — no change needed (still consumes `/api/explorer/organization`), but add a doc note if desired.
- `streamlit_app\pages\explorer.py` — render a new "Company directory" section (table of all employees: name, uid, department, role, email). Reason: gives every user a company-wide people view.

**Tests to update:**
- `tests\unit\test_organization_explorer_service.py` — assert `people` contains users from all departments, not just the caller's scope.
- `tests\contract\test_explorer_api.py` — assert response model now includes `people`.
- `tests\contract\test_streamlit_management_pages.py` — keep the explorer page read-only client assertions intact.

**New files:** none required (field added to existing response). Add `tests\unit\test_people_directory.py` if separating the directory logic into its own method is preferred.

---

## 2. Logged out after refresh

**Why:** auth is held only in `st.session_state["auth"]` (`streamlit_app\app.py:10-34`). Streamlit session state is not reliably preserved across a browser refresh / new WebSocket session, so `auth` resets to `None` and the user lands on the login screen even though their JWT (`access_token`) is still valid for `AUTH_TOKEN_EXPIRE_MINUTES` (app\core\settings.py:50).

**Files to change:**
- `streamlit_app\app.py` — after a successful login, persist `access_token` + `uid` into `st.query_params`; on every run, if `auth` is missing but `access_token` is present in `st.query_params`, restore `st.session_state.auth` from it (and validate against `/api/users/me/profile`); clear the query params on logout. Reason: the token survives a refresh and is restored without a new login.
- `streamlit_app\services\authentication_service.py` — add helper methods `restore_session(auth_dict)`/`clear_session()` and a `validate_token(token)` that calls the existing `GET /api/users/me/profile` to confirm the restored token is still valid (401 → force log-in). Reason: keep session logic out of `app.py` and out of the pages.
- `streamlit_app\pages\organization.py:123` (`st.session_state.get("auth")`) — route through the shared restore helper so it behaves identically after a refresh.
- All other service clients (`admin_api.py`, `organization_service.py`, `document_service.py`, `chat_service.py`, `profile_api.py`, `explorer_api.py`) read `st.session_state["auth"]` via `_session_token()`; **no change needed** once `app.py` restores the value on startup.

**New files to add:**
- `streamlit_app\services\session_store.py` — single module that reads/writes/clears the auth token from `st.session_state` and `st.query_params`. Reason: one shared implementation reused by `app.py`, `authentication_service.py` and every page; avoids duplicating query-param logic across seven service clients.

**Tests to add:**
- `tests\contract\test_session_persistence.py` — contract-style test asserting `session_store` persists and restores a token and that `app.py`/services keep consuming `st.session_state["auth"]` (no SQLite, no backend authorization in the page).

---

## 3. Projects page error message on Streamlit

**Why:** On `streamlit_app\pages\projects.py`, the "Members" and "Documents" columns call `admin.list_project_members(detail_id)` and `admin.list_project_documents(detail_id)` for every selected project (`projects.py:110-148`). The backend endpoints gate these on project-management scope (`app\use_cases\organization\membership_management.py:84-85` raises `ForbiddenError("Project is outside manager scope")`; `document_management.list_project_documents` likewise). A regular Developer/Tester who can *view* a project therefore sees a red `st.error` ("Project is outside manager scope") on the Projects page. Secondary defects: manual free-text "Project ID" (`projects.py:45`) fights the auto-generated business IDs, and lookups such as `department_options[department_name]` (`projects.py:54`) can KeyError when a list was empty.

**Files to change:**
- `app\api\schemas\organization.py` — add `can_manage: bool` to `ProjectResponse`. Reason: the page needs to know, per project, whether the signed-in user may manage it *before* it calls the members/documents endpoints.
- `app\use_cases\organization\project_management.py` — in `list_projects` (line 129), compute and attach `can_manage` using `self.authorization.can_manage_project(...)` for each returned project. Reason: surfaces authorization status without leaking anything extra.
- `streamlit_app\pages\projects.py` — (a) only fetch members/documents when `detail.get("can_manage")` is true, otherwise show a caption ("Members and documents are available to the project manager or department manager"); (b) guard `department_options[department_name]`/KeyErrors when lists are empty; (c) remove the manual "Project ID" text input so `create_project` uses the auto-generated `PROJ-###`; (d) keep the friendly 403 handling as a fallback. Reason: removes the spurious error and makes the page robust to empty/unauthorized data.
- `app\api\schemas\organization.py`/`app\use_cases\organization\project_management.py` — normalize blank `project_id` to `None` in `create_project` so it always auto-generates when not supplied.

**Tests to update:**
- `tests\integration\test_project_management_e2e.py` — assert non-manager `GET /api/projects` responses include `can_manage=false` and page-level data loads are not shown as errors.
- `tests\contract\test_projects_api.py` — update `ProjectResponse` contract for the new `can_manage` field and auto-generated project ID.
- `tests\contract\test_streamlit_management_pages.py` — assert the Projects page no longer unconditionally fetches members/documents for every project.

**New files:** none.

---

## 4. Admin/Manager may edit and delete users and documents after creation

**Why (current gaps):**
- Users: `PATCH /api/users/{uid}` and `DELETE /api/users/{uid}` exist (`app\api\routes\organization.py:151-174`) and `update_user`/`deactivate_user` exist (`app\use_cases\organization\user_management.py:141-177`), but they only do soft state changes and are not gated by the `USER_UPDATE`/`USER_DELETE` RBAC permissions — so "allowed" is not consistently enforced or verifiable, and there is no real deletion.
- Documents: there is **no update/edit endpoint at all**. `DocumentManagementService` has only `register_document` and `delete_document` (`app\use_cases\organization\document_management.py:79-149`); the API has no `PATCH /documents/{id}`. Admins/managers therefore cannot modify or edit an existing document.

**Files to change:**
- `app\use_cases\organization\user_management.py` —
  - Gate `update_user` and `deactivate_user` behind `USER_UPDATE` / `USER_DELETE` via `self.authorization.can(...)` (admin bypasses; manager honored within department scope).
  - Add `delete_user(actor_uid, uid)` — hard delete for admins (and same-department managers) using `uow.users.delete` plus cleanup of the user's department/project memberships and document grants (`uow.department_members`, `uow.memberships`, `uow.document_grants`). Reason: the requirement explicitly includes *delete*; hard delete is available at the repository/port level (`app\domain\ports\organization_repositories.py:24`, repositories.py:168).
- `app\api\schemas\organization.py` — `UserUpdate` stays; no new schema needed for delete.
- `app\api\routes\organization.py` — keep `PATCH /users/{uid}`; change `DELETE /users/{uid}` semantics to the new hard `delete_user` (still `204`). Reason: one endpoint for "delete" that now actually deletes (memberships/grants cleaned up) while keeping deactivate available via PATCH `status`.
- `app\use_cases\organization\document_management.py` — add `update_document(principal, document_id, changes)` allowing admin and managing-managers (via `authorization.can_manage_document`) to edit metadata: `document_name`, `description`, `version`, `file_type`, and re-assign `project_id`. Reason: adds the missing *modify/edit* capability for documents.
- `app\api\schemas\documents.py` — add `DocumentUpdate` model (optional `document_name`, `description`, `version`, `file_type`, `project_id`).
- `app\api\routes\documents.py` — add `PATCH /documents/{document_id}` returning `DocumentResponse`. Reason: exposes document editing to the UI.
- `streamlit_app\pages\users.py` — keep "Manage user"; add an explicit "Delete user" action (danger, confirmation) calling `admin.delete_user`; keep deactivate/reactivate.
- `streamlit_app\pages\documents.py` — add an "Edit document" form (rename, description, version, project) next to the existing archive action.
- `streamlit_app\services\admin_api.py` — add `update_document(document_id, payload)` and `delete_user(uid)`; keep existing clients.
- `app\domain\services\permission_catalog.py` + `app\infrastructure\persistence\rbac_seed.py` — the catalog already defines `USER_UPDATE`, `USER_DELETE`, `DOCUMENT_UPDATE`, `DOCUMENT_DELETE` and the Admin/Manager seeds already carry them; **no seed change required**, but verify seeding is applied on existing databases (call `seed_rbac` at startup if not already).

**Tests to update:**
- `tests\unit\test_user_management.py` — permission-gated update/delete and hard-delete cleanup assertions.
- `tests\unit\test_document_management.py` — `update_document` success + `ForbiddenError` for non-managers.
- `tests\contract\test_user_management_api.py`, `tests\contract\test_document_management_api.py` — PATCH/PATCH-delete contract coverage.
- `tests\integration\test_user_management_e2e.py`, `tests\integration\test_document_management_e2e.py` — e2e update/delete flows for admin and manager.

**New files:**
- `app\api\routes\` (no new file — route added to `documents.py`).
- `tests\integration\test_document_update_delete_e2e.py` — end-to-end coverage of the new document update/delete + user edit/delete paths.

---

## 5. UID auto-created

**Why:** `UserCreate.uid` is required (`app\api\schemas\organization.py:27`), and `streamlit_app\pages\users.py:55` forces the user to type a UID. The backend already has a business-ID generator for employees (`app\domain\services\business_id_generator.py:91` → `MSS-001`), but it is only used for `employee_id`, not `uid`.

**Files to change:**
- `app\api\schemas\organization.py` — make `UserCreate.uid: str | None = Field(default=None)`. Reason: UID becomes optional; the server owns identity generation.
- `app\use_cases\organization\user_management.py` — in `create_user` (line 92), when `uid` is blank/None, generate it via `self.business_id_generator.next(uow, "user")` and default `username` to it (unless a username was supplied). Keep the existing duplicate checks. Reason: guarantees a unique, monotonic UID is always created.
- `streamlit_app\pages\users.py` — remove the UID text input and surface the generated UID in the success message. Reason: admins no longer invent UIDs.

**Tests to update:**
- `tests\unit\test_user_management.py` — auto-UID assertions (unique, `MSS-###` format, duplicates rejected).
- `tests\contract\test_user_management_api.py` — `POST /api/users` without `uid` returns `201` with a generated `uid`.
- `tests\integration\test_user_management_e2e.py` (e.g. in `test_employees_and_departments.py`) — e2e auto-generation.

**New files:** none.

---

## 6. Dept ID auto-created

**Why:** `create_department` only auto-generates when `department_id is None` (`app\use_cases\organization\user_management.py:46-47`), but the UIs (`streamlit_app\pages\departments.py:35`, `streamlit_app\pages\users.py:43`) force a free-text "Department ID". Sending `""` triggers the schema `min_length=1` 400 instead of generating `DEPT-###`.

**Files to change:**
- `app\use_cases\organization\user_management.py` — in `create_department`, treat blank/whitespace ids as `None` (`if not department_id or not department_id.strip(): department_id = ...next(...)`). Reason: empty input now means "generate".
- `streamlit_app\pages\departments.py` — remove the "Department ID" text input from the create form.
- `streamlit_app\pages\users.py` — remove the "Department ID" text input from the "Add department" expander.
- `app\api\schemas\organization.py` — `DepartmentCreate.department_id` is already optional; keep as-is.

**Tests to update:**
- `tests\unit\test_user_management.py` (department section) — blank id → auto `DEPT-###`, duplicates rejected.
- `tests\contract\test_user_management_api.py` — `POST /api/departments` without id returns generated id.

**New files:** none.

---

## 7. Document ID auto-generated (not free text)

**Why:** the UI allows arbitrary text as the document ID (`streamlit_app\pages\documents.py:56` and `:76`), and although `register_document` falls back to the generator when `document_id` is falsy (`app\use_cases\organization\document_management.py:94`), whitespace strings can leak through and free-text IDs let users create inconsistent identifiers. Requirement: document IDs must be system-generated (`DOC-###`).

**Files to change:**
- `streamlit_app\pages\documents.py` — remove the "Document ID" text inputs from both the upload form and the (to-be-removed, see #8) metadata form. Reason: IDs are always `DOC-###`.
- `app\use_cases\organization\document_management.py` — in `register_document`, normalize blank/whitespace `document_id` to `None` before generating (and reject an explicitly non-blank id? keep accepting explicitly supplied ids for migration, but the UI never sends one).
- `app\api\schemas\documents.py` — `document_id` already optional; keep.

**Tests to update:**
- `tests\unit\test_document_metadata.py`, `tests\unit\test_document_management.py` — assert auto-generated `DOC-###` ids when none supplied.

**New files:** none.

---

## 8. RegisterDocument (metadata only) removed

**Why:** the "Register document (metadata only)" flow (`streamlit_app\pages\documents.py:74-90`) creates a document record with no content, so it is never provisioned for Q&A and produces dead metadata rows. Requirement: only real uploads (with content) are allowed.

**Files to change:**
- `streamlit_app\pages\documents.py` — delete the "Register document (metadata only)" expander entirely. Reason: removes the UI affordance.
- `app\use_cases\organization\document_management.py` — in `register_document`, raise `ValueError("A document must be uploaded with content or a source path")` when neither `source_path` nor `content` is provided. Reason: enforces at the service/API boundary that no content-less (metadata-only) document can be created.
- `app\api\routes\documents.py` — `POST /documents` stays, but is now upload-only by construction.

**Tests to update:**
- `tests\unit\test_document_metadata.py`, `tests\integration\test_document_metadata_persistence.py` — remove/adjust metadata-only cases to upload with content; assert content-less registration is rejected.

**New files:** none.

---

## 9. Admin can change access on unassigned documents after upload

**Why:** access management (`app\use_cases\organization\document_access.py`) gates grant/list/revoke on `can_manage_document` (`app\domain\services\authorization_engine.py:360-376`). For an unassigned document this returns true only for role "manager", and after upload the Documents page's "Access configuration" block is driven by `list_documents` (read-filtered). Requirement: admins must be able to grant/revoke access on unassigned documents they uploaded/own.

**Files to change:**
- `app\domain\services\authorization_engine.py` — make `can_manage_document` explicitly return `True` for admins on unassigned (`project_id is None`) documents (admin already short-circuits at the top; add an explicit, documented branch for managers too so unassigned-document management scope is **only** admin + manager). Reason: clear, testable scope for unassigned documents.
- `app\use_cases\organization\document_access.py` — add explicit handling/note in `grant`, `list`, `revoke` so unassigned documents are manageable by admins (and same-department managers) regardless of project linkage. Reason: closes the gap where a grant on an unassigned doc could be blocked by project-scope checks.
- `streamlit_app\pages\documents.py` — ensure the "Access configuration" section is visible for unassigned documents to admins (it already lists read-filtered docs; unassigned docs are readable by admins/managers — add a hint after upload: "Access was set to unassigned; configure grants below"). Optionally show unassigned docs even when the uploader is a manager.
- `streamlit_app\services\admin_api.py` — already exposes `list_document_access_grants` / `grant_document_access` / `revoke_document_access`; no change needed.

**Tests to update:**
- `tests\unit\test_document_upload_authorization.py`, `tests\unit\test_document_access_service.py` — admin grant/revoke on unassigned doc succeeds; non-manager fails.

**New files:**
- `tests\integration\test_document_access_unassigned_e2e.py` — upload as unassigned, then admin grants role/user access and revokes it via the API end-to-end.

---

## 10. Answer questions whose content lives in images / photos / graphs / charts

**Problem (current behavior):** the pipeline is text-only end to end.
- Ingestion accepts only `.docx`, `.txt`, `.md`, `.rst` (`app\use_cases\ingestion\document_processing.py:9`).
- `.docx` extraction reads only top-level paragraphs (`document_processing.py:95-98`, `python-docx` `document.paragraphs`). Embedded images, charts, and any text inside tables/text boxes/headers are dropped.
- No OCR, no vision model, no captioning step exists anywhere (`requirements.txt` has no OCR/image dependency).
- Chunks are embedded with the **text-only** `sentence-transformers/all-MiniLM-L6-v2` transform (`app\infrastructure\vector\chroma_client.py:33`), stored as text in ChromaDB.
- Retrieval + answer are text-only: Chroma text query (`chroma_client.py:57-102`) → LLM prompt built by `RAGContextBuilder` (`app\use_cases\chat\rag_context_builder.py`). The LLM providers are text chat clients only (`app\domain\services\llm_provider.py`, `openrouter_client.py`, `groq_client.py`).

**Result:** if a concept exists in a document only as an image/photo/graph (e.g., a flowchart, org chart, or a policy diagram), it is never indexed, retrieval finds nothing, and the bot answers "I could not find that information…" — it cannot answer from that image.

**How it will be done (phase A — OCR/caption at ingest, the required fix):**
1. Add OCR dependency and configurable settings.
2. Extract embedded raster media from `.docx` (read the package parts via `python-docx` `document.part.related_parts`, i.e. `word/media/*`); also accept direct image uploads (`.png`, `.jpg`, `.jpeg`).
3. Run OCR (Tesseract via `pytesseract`) on each image to produce text; when OCR yields little text (graphs/charts), optionally run a multimodal captioner to describe the visual (disabled by default).
4. Convert that image-derived text into **extra chunks** carrying the **same** `project_id`/`document_id` metadata as text chunks, so the existing authorization filter (`project_id` `$in` where-clause, `chroma_client.py:70-78`) and citation flow keep working unchanged.
5. Embed the merged (text + image-derived) chunks with the existing text embedding model — no vector-store or retrieval-schema change required.

(Phase B — genuine multimodal answers that show/describe the actual image via a vision LLM — is deferred; note below.)

**Existing files to modify and why:**
- `requirements.txt` — add `pytesseract` and `Pillow`. Why: OCR needs a Tesseract wrapper and image decoding (Pillow is also already a transitive dep of python-docx/PIL usage, make it explicit).
- `app\core\settings.py` — add `TESSERACT_CMD` (Windows needs the tesseract.exe path), `OCR_LANGUAGES` (default `eng`), and `IMAGE_CAPTIONING_ENABLED` (default `false`). Why: OCR is environment-dependent; the path to the Tesseract binary must be configurable per machine (this project runs on Windows).
- `.env.example` — document the three new env vars above. Why: keeps run configuration discoverable.
- `app\use_cases\ingestion\document_processing.py` — add `extract_document_text_and_images(content, file_name)` returning `(text, list[dict])` of image assets; keep the existing `extract_text_from_bytes` signature for backwards compatibility. Extend `build_chunk_records` to accept image-title/Caption text and emit chunks with extra metadata `asset_type="image"` and `asset_index`, producing one merged, sequentially-indexed chunk list (chunk ids stay unique via `{document_id}-{index}`). Why: the docx parser must surface embedded media, and chunk metadata must mark which content came from an image.
- `app\infrastructure\ingestion\provisioner.py` — extend `SUPPORTED_EXTENSIONS` with `.png`, `.jpg`, `.jpeg`; in `_detect_extension` recognize image magic bytes (`\x89PNG\r\n\x1a\n`, `\xff\xd8\xff`); in `provision_document`, after text extraction call the image extractor, run OCR, merge image-text chunks, and save extracted image assets under `DOCUMENTS_DIR` (mirroring the existing text-file destination logic at provisioner.py:68-73). Why: wires the image pipeline into provisioning so uploaded docs/images are actually indexed.
- `streamlit_app\pages\documents.py` — add `"png", "jpg", "jpeg"` to the `st.file_uploader` types (documents.py:53). Why: lets an admin upload a standalone image directly instead of only inside a docx.
- Tests referenced below.

**Existing files deliberately NOT changed (why):**
- `app\infrastructure\vector\chroma_client.py`, `app\use_cases\chat\retrieval_service.py`, `app\use_cases\chat\rag_context_builder.py`, `app\use_cases\chat\query_orchestrator.py` — Phase A indexes image content as text, so the retrieval/embedding/answer path is untouched. This keeps the change small and preserves the existing authorization scoping.
- `app\domain\services\llm_provider.py`, `openrouter_client.py`, `groq_client.py` — Phase A needs no vision model; changing the LLM contract is deferred to Phase B.

**New files to add and why:**
- `app\infrastructure\ingestion\ocr.py` — thin, mockable wrapper over `pytesseract` (`ocr_image(image_bytes, languages) -> str`). Why: gives a seam to unit-test the pipeline without a real Tesseract binary installed.
- `app\infrastructure\ingestion\image_extractor.py` — extracts embedded images from `.docx` package parts (and validates direct image uploads), returns `list[ImageAsset]` (bytes, extension, detected mime). Why: keeps all zip/media handling out of `document_processing.py` and `provisioner.py`, isolated and testable.
- `app\infrastructure\ingestion\captioner.py` — optional multimodal captioning step (used only when `IMAGE_CAPTIONING_ENABLED=true`); produces a short visual description for graphs/charts whose OCR text is sparse. Why: OCR alone often returns nothing useful for diagrams; captioning is the upgrade path without changing the retrieval schema.
- `tests\unit\test_ocr_wrapper.py` — asserts the OCR wrapper returns stubbed text and that image decoding failures surface as a `ValueError`. Why: guards the new seam.
- `tests\unit\test_image_extractor.py` — in-memory `.docx` with an embedded image fixture → asserts media extraction, direct-image handling, and merged chunk metadata (`asset_type="image"`). Why: unit-level guard for the new ingestion path.
- `tests\integration\test_document_image_ingestion_e2e.py` — build a docx with an embedded image + stubbed OCR, provision it, then assert the image-derived chunk is embedded in Chroma and retrieved by a query about the pictured concept, with correct `project_id` scoping. Why: end-to-end proof that a user can now get an answer whose source is an image inside a document.

**Phase B (deferred, optional):** genuinely multimodal answers — store extracted images, return them in retrieval results, and pass image bytes to a vision-capable LLM (e.g., a Claude/GPT-4o-class model via `OpenRouterClient`). This requires extending `LLMProvider` (app\domain\services\llm_provider.py) and `RAGContextBuilder`/`QueryOrchestrator` to carry image content, plus a retrieval step that can serve assets. Not part of this change unless explicitly requested.

**Tests to run:**
- `.\.venv\Scripts\python.exe -m pytest tests\unit tests\contract -q -p no:cacheprovider`
- `.\.venv\Scripts\python.exe -m pytest tests\integration -q -p no:cacheprovider`
- `python -m compileall -q app streamlit_app tests` after edits.

---

## Cross-cutting notes / verification

- **New files added on top of the codebase:**
  - `streamlit_app\services\session_store.py` — session persistence (requirement 2).
  - `tests\contract\test_session_persistence.py` — session-restore contract (requirement 2).
  - `tests\unit\test_people_directory.py` — company directory unit coverage (requirement 1, optional if folded into existing explorer test).
  - `tests\integration\test_document_update_delete_e2e.py` — document/user edit+delete e2e (requirement 4).
  - `tests\integration\test_document_access_unassigned_e2e.py` — unassigned access e2e (requirement 9).
  - `app\infrastructure\ingestion\ocr.py` — mockable Tesseract OCR wrapper (requirement 10).
  - `app\infrastructure\ingestion\image_extractor.py` — `.docx` embedded-media + direct image extraction (requirement 10).
  - `app\infrastructure\ingestion\captioner.py` — optional multimodal captioning for graphs/charts (requirement 10).
  - `tests\unit\test_ocr_wrapper.py`, `tests\unit\test_image_extractor.py`, `tests\integration\test_document_image_ingestion_e2e.py` — image-ingestion test coverage (requirement 10).

- **Verification commands** (already used by this repo):
  - `.\.venv\Scripts\python.exe -m pytest tests\unit tests\contract -q -p no:cacheprovider`
  - `.\.venv\Scripts\python.exe -m pytest tests\integration -q -p no:cacheprovider`
  - `python -m compileall -q app streamlit_app tests` after edits.
  - Manual: run `uvicorn app.main:app --host 127.0.0.1 --port 8000` + `streamlit run streamlit_app/app.py`; log in, refresh the browser and confirm the session persists.
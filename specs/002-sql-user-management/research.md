# Research: SQL Organization Access and User Management

## Decision: Use SQLite behind domain ports

**Rationale**: The feature requires foreign keys, unique constraints, transactions, and indexed authorization joins. SQLite provides a lightweight file-based database that fits the Department, Project, User, and membership relationships while keeping the domain independent of a concrete driver. The existing modular monolith can place ports in `app/domain/` and the adapter in `app/infrastructure/`.

**Alternatives considered**: A pure in-memory design was rejected because data must persist across test runs and CI sessions. Direct SQL calls from routes were rejected because they would violate the existing domain/infrastructure boundaries.

## Decision: Model the ERD with four domain entities and one associative table

**Rationale**: `User`, `Department`, and `Project` are the business entities from the corrected ERD. User-project membership is intrinsically many-to-many, so the database needs an associative `user_project` table with a composite uniqueness constraint. `Role` and `Permission` remain attributes/rules, not entities or tables.

**Alternatives considered**: A fixed role enum or Role table was rejected because new company-defined roles must not require schema changes. A JSON project list on User was rejected because it cannot enforce referential integrity or efficient joins.

## Decision: Authorize before vector retrieval

**Rationale**: The constitution requires identity and record-level authorization before retrieval. The chat request will carry an authenticated principal and optional project scope. An authorization service resolves allowed project IDs, and the vector adapter receives those IDs as a filter. Unauthorized project requests fail before Chroma is queried.

**Alternatives considered**: Retrieving broadly and filtering citations afterward was rejected because restricted data would already have entered the retrieval and LLM path. Treating arbitrary role strings as project access was rejected because access is based on explicit membership, with only Admin receiving organization-wide access.

## Decision: Scope Manager operations through department ownership

**Rationale**: A department contains users and projects, making department ownership the smallest clear organizational scope in the ERD. A Manager can manage records and memberships only when the target user and project belong to the Manager's department. Admin bypasses department scope.

**Alternatives considered**: A separate Permission table was rejected by the corrected ERD. A hard-coded list of every future role was rejected because organizational roles are dynamic.

## Decision: Add explicit audit records for management and denied access

**Rationale**: CRUD, membership, and authorization outcomes need actor, target, timestamp, and outcome data. Structured audit records support troubleshooting without storing passwords, tokens, or raw document text.

**Alternatives considered**: Plain application logs alone were rejected because they do not provide durable relational linkage or reliable transaction boundaries.

## Decision: Use migrations and repository contract tests

**Rationale**: Schema changes need repeatable deployment and rollback review. Repository contract tests can run against a temporary SQL database or a configured PostgreSQL test database, while authorization unit tests use fakes for fast feedback.

**Alternatives considered**: Creating tables at application startup was rejected because it obscures schema history and can race in multi-worker deployments.

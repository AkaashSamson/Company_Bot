# Research: SQL Organization Access and User Management

## Decision: Use database-agnostic persistence ports with a configurable relational adapter

**Rationale**: The feature requires foreign keys, unique constraints, transactions, and indexed authorization joins. Domain ports and use cases must not depend on a database vendor. A shared relational adapter can use SQLite initially and PostgreSQL later through configuration, while a factory supplies repositories and a Unit of Work to FastAPI. The existing modular monolith can place ports in `app/domain/` and adapters in `app/infrastructure/persistence/`.

**Alternatives considered**: A pure in-memory design was rejected because data must persist across test runs and CI sessions. Separate business logic for SQLite and PostgreSQL was rejected because it would duplicate use cases. Direct SQL calls from routes were rejected because they would violate the existing domain/infrastructure boundaries.

## Decision: Keep Streamlit as a thin client of the existing FastAPI application

**Rationale**: User, project, and document management pages should call the same FastAPI base URL as chat. Streamlit owns navigation and form state; FastAPI owns authentication, validation, authorization, persistence, and ingestion orchestration. This avoids a second API and prevents the UI from connecting directly to SQLite, PostgreSQL, Chroma, or the filesystem.

**Alternatives considered**: Direct Streamlit database access was rejected because it duplicates authorization and couples the UI to persistence. A separate management API was rejected because it increases deployment and authentication complexity.

## Decision: Model the ERD with four domain entities and one associative table

**Rationale**: `User`, `Department`, `Project`, and `Document` are the business entities from the corrected ERD. User-project membership is intrinsically many-to-many, while Project-Document is one-to-many with partial participation. The database needs an associative `user_project` table with a composite uniqueness constraint. `Role` and `Permission` remain attributes/rules, not entities or tables.

**Alternatives considered**: A fixed role enum or Role table was rejected because new company-defined roles must not require schema changes. A JSON project list on User was rejected because it cannot enforce referential integrity or efficient joins.

## Decision: Authorize before vector retrieval

**Rationale**: The constitution requires identity and record-level authorization before retrieval. The chat request will carry an authenticated principal and an optional project scope. Without a selected project, authorization resolves all allowed project IDs; with one, the service intersects it with the allowed set. The retrieval adapter receives only the resulting IDs as a filter. Unauthorized project requests fail before Chroma is queried.

**Alternatives considered**: Retrieving broadly and filtering citations afterward was rejected because restricted data would already have entered the retrieval and LLM path. Treating arbitrary role strings as project access was rejected because access is based on explicit membership, with only Admin receiving organization-wide access.

## Decision: Scope Manager operations through department ownership

**Rationale**: A department contains users and projects, making department ownership the smallest clear organizational scope in the ERD. A Manager can manage records and memberships only when the target user and project belong to the Manager's department. Admin bypasses department scope.

**Alternatives considered**: A separate Permission table was rejected by the corrected ERD. A hard-coded list of every future role was rejected because organizational roles are dynamic.

## Decision: Use migrations and repository contract tests

**Rationale**: Schema changes need repeatable deployment and rollback review. Repository contract tests can run against a temporary SQL database or a temporary SQLite database, while authorization unit tests use fakes for fast feedback.

**Alternatives considered**: Creating tables at application startup was rejected because it obscures schema history and can race in multi-worker deployments.

# Job Hub Architecture

## Architecture Goals

Job Hub uses a deliberately simple architecture appropriate to a personal job
application tracking application and a realistic software quality engineering
portfolio.

The architecture shall:

- Support practical application tracking and preservation of job information.
- Provide realistic targets for software quality and test automation.
- Favor maintainability, readability, and clarity over unnecessary complexity.
- Preserve relational integrity through a normalized database design.
- Support future expansion without implementing future requirements prematurely.
- Introduce additional technologies only when an identified requirement
  justifies them.

This document describes the Phase 1 technical design supporting
[the MVP requirements](mvp-requirements.md). The requirements define product
behavior; this document defines its architectural support. Detailed test cases
belong in the Phase 1 test strategy and implementation work.

## Phase 1 Application Architecture

The Phase 1 application uses Python, Flask, SQLite, HTML/CSS, and minimal
JavaScript. Selenium WebDriver and Pytest provide the primary UI automation
framework.

The browser presents application forms, lists, and detail views. Flask handles
requests, validates and normalizes input, applies business rules, and coordinates
database operations. SQLite persists application and reference data between
sessions. Ordinary application startup shall not reset existing data.

Presentation, business rules, and persistence responsibilities shall be organized
clearly enough to test and maintain them independently where useful. This does
not require separate services, a generalized repository framework, or additional
deployment components. Straightforward modules and functions are sufficient.

The application targets the expected scale of a personal job-search database and
the Chromium-based browser used for development and automated testing. Normal
operations shall avoid unnecessary delay; enterprise-scale infrastructure is
outside Phase 1 scope.

## Phase 1 Data Architecture

### Design Principles

The Phase 1 database is designed to at least Third Normal Form (3NF).
Normalization reduces duplication and maintains data integrity. It does not
require every fixed categorical value to have a separate table. Small, stable
enumerations remain constrained attributes when a separate entity adds no
meaningful value.

Phase 1 begins when a job application has been submitted. Pre-application
opportunities and discarded positions are reserved for a future phase.

### Core Entities

The Phase 1 data model contains exactly six entities:

- `COMPANY`
- `LOCATION`
- `APPLICATION`
- `SOURCE`
- `STATUS`
- `APPLICATION_STATUS_HISTORY`

Company headquarters, job location, and work arrangement represent different
facts. Headquarters belongs to the company; job location belongs to the
application; work arrangement describes how work is performed. `REMOTE` is not
a geographic location.

## Entity Definitions

The following definitions describe the logical schema. Exact SQLite data types,
constraint syntax, and normalization/index mechanisms are implementation
decisions, subject to the integrity rules in this document.

### COMPANY

Represents an organization to which one or more applications have been submitted.

| Field | Definition |
| --- | --- |
| `company_id` | Primary key. |
| `name` | Required company name. |
| `hq_location_id` | Optional foreign key to `LOCATION`; null when headquarters is unknown. |
| `created_at` | Timestamp when the record was created. |
| `last_updated_at` | Timestamp when the record was last modified. |

Company names shall be unique using normalized comparison that ignores letter
case and insignificant leading or trailing whitespace.

A company may have multiple applications and one optional headquarters location
in Phase 1. Selecting an existing company uses its existing headquarters location.
Changing an application's company shall therefore display the selected company's
headquarters rather than carry over the previous company's headquarters.

Headquarters changes modify shared company data. When a company-level change
affects information shared by multiple applications, the user must confirm it
before persistence, as specified by FR-006.

### LOCATION

Represents a geographic location reusable by companies and applications.

| Field | Definition |
| --- | --- |
| `location_id` | Primary key. |
| `city` | City or locality. |
| `state_province` | State, province, or equivalent administrative area. |
| `country` | Country. |
| `created_at` | Timestamp when the record was created. |
| `last_updated_at` | Timestamp when the record was last modified. |

Equivalent normalized combinations of city, state/province, and country shall
reuse an existing location rather than create duplicates. Comparison shall treat
case, insignificant surrounding whitespace, and absent optional components
consistently. The implementation must account for missing components when
enforcing equivalence.

The same location can serve as company headquarters and job location without
conflating those relationships. Unknown headquarters or job location is
represented by a null foreign key rather than requiring a placeholder location.

### SOURCE

Represents the channel through which a position was identified, such as a company
career site, job board, recruiter, or direct outreach.

| Field | Definition |
| --- | --- |
| `source_id` | Primary key. |
| `name` | Required source name. |
| `created_at` | Timestamp when the record was created. |
| `last_updated_at` | Timestamp when the record was last modified. |

Source names shall be unique using normalized comparison that ignores letter
case and insignificant leading or trailing whitespace. Sources are reference
data because available channels may change over time.

### STATUS

Represents an application lifecycle state.

| Field | Definition |
| --- | --- |
| `status_id` | Primary key. |
| `name` | Required, unique status name. |
| `is_terminal` | Indicates whether the status represents a terminal application state. |
| `display_order` | Controls logical presentation order. |
| `created_at` | Timestamp when the record was created. |
| `last_updated_at` | Timestamp when the record was last modified. |

Initial values may include:

- `APPLIED`
- `SCREENING`
- `INTERVIEWING`
- `OFFER`
- `ACCEPTED`
- `REJECTED`
- `WITHDRAWN`
- `CLOSED`

Status is reference data with presentation and lifecycle metadata.
`display_order` does not determine event chronology. Terminal status does not
mean archived, and `ARCHIVED` is not an application lifecycle status.

### APPLICATION

Represents a submitted job application.

| Field | Definition |
| --- | --- |
| `application_id` | Primary key. |
| `company_id` | Required foreign key to `COMPANY`. |
| `job_location_id` | Optional foreign key to `LOCATION` for the position. |
| `source_id` | Required foreign key to `SOURCE`. |
| `job_title` | Required position title. |
| `external_job_id` | Optional employer or source requisition identifier. |
| `job_url` | Optional original job posting URL. |
| `job_description` | Optional captured job description text. |
| `work_arrangement` | Optional constrained value: `ONSITE`, `HYBRID`, or `REMOTE`. |
| `employment_type` | Optional constrained employment relationship, such as full-time, part-time, contract, or temporary. |
| `compensation_min` | Optional numeric minimum advertised compensation. |
| `compensation_max` | Optional numeric maximum advertised compensation. |
| `compensation_basis` | Constrained period, initially `ANNUAL` or `HOURLY`; required when either compensation bound is present. |
| `application_date` | Required date the application was submitted. |
| `notes` | Optional free-form application notes. |
| `archived_at` | Nullable timestamp recording archival; null means active. |
| `created_at` | Timestamp when the record was created. |
| `last_updated_at` | Timestamp when the record was last modified. |

Compensation is structured numeric data rather than display text, allowing later
filtering, sorting, or analysis. Either bound can be supplied independently;
when both are present, minimum shall not exceed maximum.

The captured job description remains available independently of the original
posting URL. Company headquarters is obtained through `COMPANY`, not copied onto
each application.

Current status is not stored on `APPLICATION`. Separate `status_id`,
`status_date`, `rejection_date`, and `closed_date` fields are unnecessary because
the lifecycle facts are represented by status history.

### APPLICATION_STATUS_HISTORY

Records application lifecycle changes over time.

| Field | Definition |
| --- | --- |
| `application_status_history_id` | Primary key. |
| `application_id` | Required foreign key to `APPLICATION`. |
| `status_id` | Required foreign key to `STATUS`. |
| `effective_at` | Required date/time when the status became effective. |
| `notes` | Optional context associated with the status change. |
| `created_at` | Timestamp when the history record was entered into Job Hub. |
| `last_updated_at` | Timestamp when the history record was last modified. |

The combination of `application_id` and `effective_at` shall be unique.
`effective_at` and `created_at` intentionally represent different facts: an event
may be recorded after it occurred.

Every application shall have at least one status-history record. This is a
transactional/business rule; an ordinary foreign-key constraint alone cannot
guarantee that every parent application has a child history row.

## Relationships

| Parent | Child | Relationship |
| --- | --- | --- |
| `LOCATION` | `COMPANY` | One location may be headquarters for many companies; each company has zero or one headquarters location. |
| `LOCATION` | `APPLICATION` | One location may be used by many applications; each application has zero or one job location. |
| `COMPANY` | `APPLICATION` | One company may have many applications; each application has one company. |
| `SOURCE` | `APPLICATION` | One source may be used by many applications; each application has one source. |
| `APPLICATION` | `APPLICATION_STATUS_HISTORY` | Each application has one or more history records; each history record belongs to one application. |
| `STATUS` | `APPLICATION_STATUS_HISTORY` | One status may be used by many history records; each history record has one status. |

Foreign-key integrity shall be enabled for every SQLite connection. Operations
on referenced data shall not leave dangling references or remove application
history unintentionally.

## Timestamp Convention

Every persisted Phase 1 table includes required `created_at` and
`last_updated_at` timestamps.

`created_at` is immutable after insertion. `last_updated_at` is initialized on
creation and maintained automatically when the persisted row changes. Users
shall not be responsible for maintaining these fields. Reusing an unchanged
reference record does not constitute a modification to that record.

Business-event dates and timestamps remain separate from persistence metadata:

- `application_date` records the submission date.
- `effective_at` records when a lifecycle status became effective.
- `archived_at` records when the application was archived.
- `created_at` and `last_updated_at` describe the persisted row.

Timestamp parsing, precision, storage, and comparison shall use a consistent
convention so that chronological ordering, equality, and future-time validation
agree. The concrete representation and timezone handling shall be documented
during implementation; application dates remain dates rather than invented
event timestamps.

## Status Lifecycle Behavior

Current status is always derived from the history record with the greatest
`effective_at` for the application. Insertion order, history primary keys,
`created_at`, and `last_updated_at` do not determine current status.

The same derivation shall be used for detail views, list display, status
filtering, and status sorting. No separate current-status cache is required for
Phase 1.

Creating an application also creates its initial history record. Initial status
defaults to `APPLIED`, but another valid status may be selected for retrospective
entry. For initial `APPLIED` status, the effective date defaults to the
application date. If that date is today, the effective time defaults to the time
of recording. For retrospective applications, the user supplies or confirms the
effective time, as required by FR-001.

Status changes append history rather than overwrite existing events. Backdated
events are permitted; future effective timestamps are prohibited. Adding an
older event does not displace a later effective event as current status.

History is displayed from oldest to newest by `effective_at`. Corrections may
change a history record's status, effective timestamp, or notes, while preserving
`created_at` and updating `last_updated_at`. Corrections must preserve timestamp
uniqueness and the prohibition on future effective timestamps.

Deleting a history record requires confirmation and shall be rejected if it
would remove the application's only remaining record. After correction or
deletion, current status follows the greatest remaining `effective_at`; no
duplicated application status needs to be synchronized.

General application editing does not modify or replace status history. A change
to `application_date`, for example, does not silently rewrite an existing
history event. Cancelled operations leave persisted data unchanged.

## Archiving and Restoration

Archiving sets `APPLICATION.archived_at` and updates its `last_updated_at`,
preserving `created_at`, application information, and all status history.
Restoring clears `archived_at` and updates `last_updated_at` while preserving the
same information. Neither operation changes lifecycle status.

The default list includes active applications only (`archived_at` is null).
Archived and All record-state filters expose historical applications using the
same search, filter, sort, and pagination behavior. Mixed lists visually
distinguish archived records.

Archiving requires confirmation. Archive and restore operations can be cancelled
without persistence. Physical application deletion is unavailable through the
Phase 1 UI.

## Transaction Boundaries

Multiple dependent writes shall succeed or fail as one database transaction.

Creating an application and its initial status-history record is one atomic
operation. Any missing company, source, or locations created specifically as
part of that operation belong to the same transaction. This includes a new
company's optional headquarters location. If any dependent write fails, all
writes from that operation are rolled back.

Application editing follows the same principle when it creates reference data
or applies a confirmed shared company change. An operation must not commit
reference-data changes and then fail to save the application they were created
or changed for. Existing, unchanged reference records are simply reused.

The check that at least one history record remains and any corresponding
deletion shall occur within the same protected write transaction. All supported
write paths shall preserve this invariant, including setup/import utilities if
such utilities are later introduced.

Normalization, validation, duplicate review, and required user confirmations
shall occur before committing changes. Do not hold a database write transaction
open while waiting for user confirmation. Integrity-sensitive conditions shall
still be checked or enforced when the write occurs.

On failure, roll back the operation and return an appropriate error response.
The user shall not receive a success response before the transaction commits.

## Reference-Data Normalization and Reuse

Application entry and editing allow selection of existing company, source, and
location records, or creation of missing records within the same workflow.
Normalization shall not force a separate administration workflow.

Matching and uniqueness enforcement shall agree:

- Company names are unique after case-insensitive, surrounding-whitespace
  normalization.
- Source names follow the same rule.
- Locations reuse equivalent normalized city, state/province, and country
  combinations, with consistent treatment of absent components.

The exact use of collations, normalized keys, indexes, or other SQLite mechanisms
remains an implementation decision. The chosen mechanism shall enforce the
required integrity behavior, including when two writes attempt to create the
same reference value. A preliminary lookup alone is not a substitute for
appropriate database enforcement.

Display text may retain meaningful capitalization. Normalized comparison does
not imply rewriting meaningful content or adding geographic alias resolution.

## Application Duplicate Detection

Potential duplicate applications are a business-rule warning, not a database
uniqueness restriction.

Company plus external job/requisition ID is the strongest duplicate indicator
when an external identifier is present. Company plus job title may provide a
weaker indicator when an identifier is unavailable.

The user can review a possible duplicate and cancel or explicitly proceed. The
database shall allow the confirmed application to be saved because repeated
applications can be legitimate. Neither company plus external job ID nor company
plus job title shall be made unique on `APPLICATION`.

## Phase 1 Data Constraints

Database constraints enforce appropriately expressible persistence rules.
Application validation supplements them with contextual business behavior and
understandable feedback, as required by FR-011 and NFR-002.

| Rule | Enforcement responsibility |
| --- | --- |
| Primary keys on all six entities | Database. |
| Valid foreign-key relationships | Database, with foreign-key enforcement enabled. |
| Mandatory persisted values | Database required-value constraints plus application validation, including rejection of blank required text. |
| Unique normalized company and source names | Database uniqueness aligned with application normalization and reuse. |
| Reuse of equivalent normalized locations | Application matching backed by appropriate database integrity enforcement. |
| Unique status names | Database. |
| Unique `(application_id, effective_at)` | Database composite uniqueness plus validation feedback. |
| Controlled work arrangement, employment type, and compensation basis | Database value constraints plus application validation; optional fields may be null. |
| Numeric compensation values | Appropriate database value/type constraints plus application parsing and validation. |
| Minimum compensation no greater than maximum when both are present | Database value constraint plus application validation. |
| Compensation basis present when either compensation value is present | Database value constraint plus application validation. |
| Valid dates and timestamps; effective timestamps not in the future | Application parsing and contextual time validation, supplemented by suitable persistence constraints. |
| At least one history record per application | Transactional business rule across creation and history deletion. |
| Syntactically valid web URL when supplied | Application validation. |
| Potential duplicate application | User-visible warning with an explicit option to proceed; no database uniqueness restriction. |

Required application input consists of company, job title, application date,
source, initial status, and initial effective date/time. The last two are
persisted in history rather than on `APPLICATION`.

Schema implementation shall not rely on a numeric-looking column declaration
alone to satisfy compensation validation. Optional values must remain optional;
unknown compensation is not zero, and unknown location is not a fabricated
geographic value.

The exact employment-type value set, location-component nullability, and physical
schema details shall be finalized during implementation consistently with the
requirements. They do not justify additional Phase 1 entities or unrelated
business restrictions.

## Input Normalization and Error Handling

Applicable short-form text shall have insignificant leading and trailing
whitespace removed before validation and persistence. Required text must remain
nonempty after normalization. Optional empty input shall be handled consistently.

Normalization shall preserve meaningful internal content, punctuation, and
whitespace in job descriptions and notes. Ordinary apostrophes, quotation marks,
and expected text characters shall be supported safely. Database writes shall
use parameterized values, and displayed user content shall be escaped
appropriately.

Invalid input shall not be persisted. Forms identify required fields and provide
clear feedback for invalid fields or conditions, preserving valid entered
information where practical. Unexpected application or database errors shall
produce an appropriate response without exposing internal implementation details.

## Read and Query Behavior

Application lists join normalized company, source, and optional job-location
data with the derived current status. Missing optional information shall not
exclude an application or cause its detail view to fail.

The list displays company, job title, job location, work arrangement, application
date, current status, and source. All seven columns support ascending and
descending sorting; the default is application date descending.

Search uses case-insensitive substring matching across company, job title, and
external job ID. Filters cover current status, source, work arrangement,
employment type, job location, application date range, and record state.
Multiple selected values within status, source, work arrangement, or employment
type combine with OR; different filter categories combine with AND.

Search and filters apply to the complete matching set before sorting and
pagination. Pagination defaults to 25 applications, returns to the first page
when search or filters change, and uses deterministic ordering for tied sort
values. Empty and no-results states receive appropriate UI feedback.

Queries and indexes shall support these operations at personal-use scale without
introducing a search service or denormalized current-status storage. Index
choices should follow actual query needs and required uniqueness constraints.

## Testability

Testability is a Phase 1 design consideration aligned with NFR-006 and the
maintainability principle in NFR-007.

- UI elements used for automated interaction expose stable, meaningful
  selectors, using semantic markup and durable identifiers where appropriate.
- Test data is controllable and reproducible, with isolated test databases and
  repeatable reference-data setup that does not reset personal data.
- Time-dependent validation and timestamp behavior can be exercised
  deterministically through a small, controllable time boundary where needed.
- Application behavior avoids unnecessary timing dependencies; UI tests can wait
  for observable completion rather than depend on arbitrary delays.
- Business validation and database behavior can be verified below the UI where
  appropriate, while Selenium and Pytest exercise user workflows.

The later test strategy should cover meaningful integrity and workflow risks:
transaction rollback, normalized reference reuse, duplicate-warning override,
retrospective status ordering, timestamp collisions, final-history deletion
prevention, archive/restore preservation, compensation validation, and persistence
across sessions. These are verification targets rather than additional product
features.

Testability shall not distort normal product behavior or require unnecessary
frameworks, production-only test endpoints, or abstraction layers.

## Future Evolution

The Phase 1 schema supports future expansion without implementing it prematurely.
Potential later capabilities include:

- Tracking opportunities before submission.
- Preserving discarded opportunities and disposition reasons.
- Recruiter, contact, and recruiting-firm management.
- Additional company locations.
- Application activities and follow-up actions.
- External job-source imports and integrations.
- Automated job discovery or analysis.

These capabilities, AI-assisted analysis, and automated application submission
are outside the Phase 1 MVP. Future requirements may introduce entities or
technologies when their need is established. Phase 1 retains the six-table
normalized model and the simple Flask + SQLite architecture.

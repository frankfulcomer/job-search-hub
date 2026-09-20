# Job Hub Phase 1 MVP Requirements

## Purpose

The Phase 1 MVP provides a practical application for recording and managing
submitted job applications.

The MVP is intended to replace the core functionality currently provided by an
applications spreadsheet while improving data structure, application status
tracking, searchability, and preservation of job information.

The MVP also provides a realistic system for demonstrating software quality
engineering and test automation practices.

## Scope

Phase 1 begins when a job application has been submitted.

Pre-application opportunities, including prospective and discarded positions,
are outside the Phase 1 scope and may be introduced in a future phase.

Phase 1 includes:

- Recording a submitted job application.
- Preserving the associated job description.
- Recording company headquarters and job location separately.
- Recording structured employment and compensation information.
- Maintaining application status history.
- Viewing and editing application information.
- Searching, sorting, and filtering applications.
- Viewing application details and lifecycle history.

Phase 1 does not include:

- Prospect or discarded-position tracking.
- Recruiter or contact management.
- Recruiting-firm management.
- Automated job discovery.
- External job-board integration.
- AI-assisted job analysis.
- Automated application submission.

## Functional Requirements

### Application Field Definitions

- **Company** - Organization to which the application was submitted.
- **Job title** - Title of the position as identified in the job posting or
  application.
- **Application date** - Date on which the application was submitted.
- **Initial status** - Application lifecycle status that is effective when the
  application is first recorded in Job Hub. This may represent a later
  lifecycle state when an existing application is entered retrospectively.
- **Initial status effective date** - Date and time when the initial status became
  effective in the application lifecycle. This may differ from both the
  application date and the date the application is entered into Job Hub.
- **Job location** - Geographic location associated with the position. This is
  independent of the company's headquarters location and work arrangement.
- **Company headquarters location** - Geographic location of the organization's
  headquarters.
- **Job description** - Captured text of the job description associated with
  the application.
- **Job URL** - URL of the original job posting or application listing.
- **External job or requisition ID** - Identifier assigned to the position by
  the employer or external source.
- **Source** - Channel through which the position was originally identified,
  such as a company career site, job board, recruiter, or direct outreach.
- **Work arrangement** - How the work is performed with respect to location,
  such as onsite, hybrid, or remote.
- **Employment type** - Nature of the employment relationship, such as
  full-time, part-time, contract, or temporary.
- **Minimum compensation** - Lower bound of the advertised or known
  compensation range.
- **Maximum compensation** - Upper bound of the advertised or known
  compensation range.
- **Compensation basis** - Time basis associated with compensation, such as
  annual or hourly.
- **Notes** - Free-form information relevant to the application that is not
  represented by another structured field.
- **Archived** - Indicates that an application has been removed from normal
  active views while remaining preserved for historical reference. Archiving
  does not change the application's lifecycle status or status history.

### FR-001 - Record an Application

The system shall allow a submitted job application to be recorded.

An application shall support the following information:

- Company - Required.
- Job title - Required.
- Application date - Required.
- Initial status - Required. Defaults to `APPLIED`, but another valid status may
  be selected when an application is entered retrospectively.
- Initial status effective date - Required. When the initial status is
  `APPLIED`, the effective date shall default to the application date. When the
  application date is the current date, the effective time shall default to the
  time at which the application is recorded. For retrospective applications,
  the user shall provide or confirm the effective time. The effective date and
  time may be changed when an existing application is entered retrospectively.
- Job location - Optional.
- Company headquarters location - Optional.
- Job description - Optional.
- Job URL - Optional.
- External job or requisition ID - Optional.
- Source - Required.
- Work arrangement - Optional.
- Employment type - Optional.
- Minimum compensation - Optional.
- Maximum compensation - Optional.
- Compensation basis - Required when minimum or maximum compensation is
  provided.
- Notes - Optional.

When both minimum and maximum compensation are provided, minimum compensation
shall not exceed maximum compensation.

Creating an application shall also create an initial application status history
record containing the selected initial status and its effective date.

### FR-002 - Detect Potential Duplicate Applications

The system shall identify potential duplicate applications during application
entry.

When an external job or requisition ID is available, the combination of company
and external job ID shall be treated as the strongest duplicate indicator.

Other application information, such as company and job title, may be used to
identify possible duplicates when an external job ID is unavailable.

Potential duplicate detection shall warn the user rather than prevent the
application from being saved.

The user shall be able to review the potential duplicate and either cancel the
new application or proceed with saving it.

### FR-003 - View Applications

The system shall provide a list view of recorded applications.

The default application list shall display:

- Company.
- Job title.
- Job location.
- Work arrangement.
- Application date.
- Current status.
- Source.

Current status shall be derived from the application's status history.

Applications shall be displayed by application date in descending order by
default, with the most recently submitted application displayed first.

The application list shall support sorting by all seven displayed columns:
Company, Job title, Job location, Work arrangement, Application date, Current
status, and Source.

Each sortable column shall support ascending and descending order. Repeated
selection of the same column shall toggle between ascending and descending
order.

Selecting an application shall provide access to the complete application
detail view.

When no applications have been recorded, the system shall display an
appropriate empty-state message rather than an empty or erroneous table.

The application list shall be paginated.

The default page size shall be 25 applications.

The user shall be able to navigate between available pages.

Sorting and filtering shall apply to the complete matching application set
before pagination is applied.

When filtering or searching changes the result set, pagination shall return to
the first page.

The system shall not display pagination controls that imply additional pages
when all matching applications fit on a single page.

### FR-004 - Search and Filter Applications

The system shall provide search and filtering capabilities for the application
list.

Free-text search shall support matching against:

- Company.
- Job title.
- External job or requisition ID.

Free-text search shall be case-insensitive and shall match the search text when
it occurs anywhere within a supported searchable field (substring matching).

The application list shall support filtering by:

- Current status.
- Source.
- Work arrangement.
- Employment type.
- Job location.
- Application date range.

Status, source, work arrangement, and employment type filters shall support
selection of multiple values.

Multiple selected values within the same filter category shall be combined
using inclusive `OR` behavior.

Filters from different categories shall be combined using `AND` behavior.

For example, selecting `SCREENING` and `INTERVIEWING` as statuses together with
`HYBRID` and `REMOTE` as work arrangements shall return applications whose:

- Current status is `SCREENING` OR `INTERVIEWING`; AND
- Work arrangement is `HYBRID` OR `REMOTE`.

Application date filtering shall support optional beginning and ending dates.

Search criteria and filters may be used individually or in combination.

The system shall provide a means to clear active search and filter criteria and
return to the complete application list.

When no applications match the active search and filter criteria, the system
shall display an appropriate no-results message.

Searching and filtering shall be applied before sorting and pagination.

Changing search or filter criteria shall return the application list to the
first page.

The application list shall support filtering by record state:

- Active.
- Archived.
- All.

The default record state shall be Active.

Archived applications shall be excluded from the default application list.

When Archived or All is selected, archived applications shall participate in
searching, filtering, sorting, and pagination using the same behavior as active
applications.

Archived applications shall be visually distinguishable from active
applications when both are displayed together.

### FR-005 - View Application Details

The system shall provide a detail view for each recorded application.

The detail view shall present application information in logical sections.

#### Application

The application section shall display:

- Job title.
- Application date.
- Current status.
- Source.
- Work arrangement.
- Employment type.
- Minimum and maximum compensation when available.
- Compensation basis when compensation is available.

#### Company and Location

The company and location section shall display:

- Company.
- Company headquarters location when available.
- Job location when available.

Company headquarters location and job location shall remain distinct even when
they reference the same geographic location.

#### Original Posting

The original posting section shall display:

- External job or requisition ID when available.
- Job URL when available.
- Captured job description when available.

When a job URL is available, the user shall be able to follow the URL to the
original posting.

The captured job description shall remain available independently of the
continued availability of the original job URL.

#### History and Notes

The history and notes section shall display:

- Application notes.
- Complete application status history.

Status history shall display each recorded status together with:

- Status effective date and time.
- Status-specific notes when available.

Status history shall be displayed in ascending order by effective date and time
(`effective_at`), from oldest to newest.

The application's current status shall be clearly identifiable from the status
history.

#### Missing Optional Information

Optional information that has not been recorded shall not cause the detail view
to fail or display misleading values.

### FR-006 - Edit an Application

The system shall allow information associated with an existing application to
be edited.

Editable application information shall include:

- Company.
- Job title.
- Application date.
- Job location.
- Company headquarters location.
- Job description.
- Job URL.
- External job or requisition ID.
- Source.
- Work arrangement.
- Employment type.
- Minimum compensation.
- Maximum compensation.
- Compensation basis.
- Notes.

The same field validation rules that apply when recording an application shall
apply when editing an application.

Editing an application shall not modify or replace application status history.

Application status shall not be changed through the general application edit
operation.

When company headquarters information is edited, the change shall apply to the
company record and therefore may affect other applications associated with the
same company.

The system shall require confirmation before applying a company-level change
that affects information shared by multiple applications.

Saving changes shall update the appropriate `last_updated_at` timestamp while
preserving the original `created_at` timestamp.

The user shall be able to cancel an edit without changing persisted application
data.

### FR-007 - Update Application Status

The system shall allow the current status of an application to be changed.

A status change shall require:

- New status.
- Status effective date and time.

A status change may include status-specific notes.

Recording a status change shall create a new
`APPLICATION_STATUS_HISTORY` record.

Existing status history shall not be overwritten when a new status is
recorded.

The newly recorded status shall become the application's current status when
its effective date and time make it the most recent effective status.

The system shall preserve the distinction between the status effective date and
time and the date and time when the status-history record was created.

The user shall be able to cancel a status change without modifying application
status history.

Status effective date and time shall not be in the future.

Status changes may be entered retrospectively.

When a status change is entered retrospectively, current status shall be
determined by the most recent `effective_at` value rather than by the order in
which status-history records were created.

Two status-history records for the same application shall not have the same
effective date and time.

### FR-008 - Correct Application Status History

The system shall allow an existing application status-history record to be
corrected when information was entered incorrectly.

The user shall be able to edit:

- Status.
- Status effective date and time.
- Status-specific notes.

A corrected effective date and time shall not be in the future.

A correction shall not result in two status-history records for the same
application having the same effective date and time.

Correcting a status-history record shall preserve the record's original
`created_at` timestamp and update its `last_updated_at` timestamp.

After a status-history record is corrected, the application's current status
shall be recalculated using the most recent `effective_at` value.

The system shall require confirmation before deleting a status-history record.

Deleting a status-history record shall cause the application's current status
to be recalculated from the remaining history.

The application shall always contain at least one status-history record. The
system shall not permit deletion of the only remaining status-history record.

The user shall be able to cancel a status-history correction without changing
persisted data.

### FR-009 - Archive and Restore an Application

The system shall allow an application to be archived without deleting the
application or its associated history.

Archiving an application shall:

- Preserve all application information.
- Preserve complete application status history.
- Preserve the application's current lifecycle status.
- Record the date and time when the application was archived.
- Remove the application from the default active application list.

Archived applications shall remain available through an archived-application
view or filter.

The system shall require confirmation before archiving an application.

The system shall allow an archived application to be restored.

Restoring an application shall:

- Clear the application's archived state.
- Return the application to the normal application list.
- Preserve all application information and status history.

Archiving or restoring an application shall update `last_updated_at` while
preserving `created_at`.

The user shall be able to cancel an archive or restore operation without
changing persisted data.

### FR-010 - Manage and Reuse Reference Data

The system shall reuse existing reference and entity records where appropriate
rather than creating duplicate records for equivalent information.

When recording or editing an application, the user shall be able to select an
existing company, location, or source.

When an appropriate record does not exist, the user shall be able to create the
required company, location, or source as part of the application workflow.

Company names shall be unique without regard to letter case or insignificant
leading or trailing whitespace.

Source names shall be unique without regard to letter case or insignificant
leading or trailing whitespace.

Locations representing the same city, state or province, and country shall be
reused rather than duplicated.

Selecting an existing company shall use the headquarters location associated
with that company.

Creating a new company shall allow an optional headquarters location to be
recorded.

Reference-data selection shall not require the user to leave an application
entry or edit workflow solely to create a missing value.

### FR-011 - Validate Input and Handle Errors

The system shall validate user-entered data before persisting changes.

Leading and trailing whitespace shall be removed from applicable text input
before validation and persistence. Meaningful internal whitespace in long-form
fields, such as job descriptions and notes, shall be preserved.

Required fields shall be clearly identified.

When validation fails:

- The requested change shall not be persisted.
- The user shall receive a clear indication of the invalid field or condition.
- Valid information already entered by the user shall be preserved where
  practical so that the entire form does not need to be re-entered.

The system shall validate relationships between fields, including:

- Minimum compensation shall not exceed maximum compensation.
- Compensation basis shall be required when compensation is provided.
- Status effective date and time shall not be in the future.
- Two status-history records for the same application shall not have the same
  effective date and time.

When a job URL is provided, it shall represent a syntactically valid web URL.

Text input shall safely support ordinary punctuation, apostrophes, quotation
marks, and other characters reasonably expected in company names, job titles,
notes, and job descriptions.

Unexpected application or persistence errors shall result in an appropriate
error response rather than exposing internal implementation details.

A failed operation shall not leave partially persisted or internally
inconsistent application data.

## Non-Functional Requirements

### NFR-001 - Usability

The application shall provide a clear and consistent user interface for common
application-management workflows.

Frequently used actions shall not require unnecessary navigation or technical
knowledge.

Forms shall identify required information and provide understandable validation
feedback.

### NFR-002 - Data Integrity

The application shall maintain relational integrity between persisted records.

Database operations involving multiple dependent changes shall not leave the
database in a partially updated or inconsistent state.

The database shall enforce appropriate primary-key, foreign-key, uniqueness,
and value constraints in addition to application-level validation.

### NFR-003 - Persistence

Application data shall persist between application sessions.

Restarting the application shall not alter or remove previously persisted data.

### NFR-004 - Browser Support

Phase 1 shall support the current Chromium-based browser used for development
and automated testing.

Additional browser support may be introduced when justified by project needs.

### NFR-005 - Performance

For the expected scale of a personal job-search database, normal application
operations such as listing, searching, filtering, viewing, and updating
applications shall complete without noticeable unnecessary delay.

Phase 1 does not require optimization for enterprise-scale workloads.

### NFR-006 - Testability

Application behavior shall be implemented in a manner that supports reliable
automated testing.

User-interface elements required for automated interaction shall be
identifiable through stable, meaningful selectors.

Test data shall be controllable and reproducible.

Application behavior shall not introduce unnecessary timing dependencies that
make automated tests unreliable.

### NFR-007 - Maintainability

The implementation shall favor straightforward, readable solutions over
unnecessary abstraction or architectural complexity.

Application and test code shall be organized sufficiently to support continued
development without introducing complexity solely for architectural purposes.
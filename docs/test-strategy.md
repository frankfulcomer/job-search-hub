# Job Search Hub Phase 1 Test Strategy

## Purpose

This document defines the testing approach for the Job Search Hub Phase 1 MVP.

The strategy supports two related goals:

- Verify that Job Search Hub satisfies its defined product requirements and maintains
  appropriate data integrity.
- Demonstrate a practical software quality engineering approach using multiple
  test levels, risk-based test selection, and continuous integration.

Testing shall be performed at the lowest practical level that provides useful
and reliable coverage. End-to-end browser automation shall complement rather
than replace lower-level testing.

## Repository Model

Phase 1 separates the application and external test automation into two
repositories.

### `job-search-hub`

The application repository contains the Job Search Hub product and tests that require
knowledge of its internal implementation.

The repository includes:

- Python and Flask application code.
- SQLite schema and persistence code.
- HTML, CSS, and minimal JavaScript.
- Unit tests.
- Database and integration tests.
- Flask application tests.

Tests in this repository may directly exercise application functions, business
logic, persistence behavior, Flask routes, and other internal interfaces.

### `job-search-hub-tests`

The external automation repository treats Job Search Hub as a system under test.

The repository contains:

- Selenium WebDriver automation.
- Pytest test execution.
- Test fixtures and controlled test data.
- Reusable browser-interaction components where they provide clear value.
- External automated regression and workflow coverage.

Tests in this repository shall interact with Job Search Hub through its externally
observable user interface rather than importing or directly exercising
application implementation code.

The separation allows application-level tests to verify internal correctness
efficiently while external automation independently verifies product behavior
from the user's perspective.

## Test Levels

### Unit Testing

Unit tests verify isolated application logic where meaningful behavior can be
tested without requiring the complete application or database.

Appropriate unit-test targets may include:

- Input normalization.
- Validation functions.
- Compensation validation.
- Status and timestamp business rules.
- Other deterministic business logic introduced during implementation.

Unit-testability shall not justify unnecessary classes, abstractions, or
architectural complexity.

### Integration Testing

Integration tests verify interaction between application code and the SQLite
persistence layer.

Coverage shall include high-risk persistence behavior such as:

- Database constraints.
- Foreign-key integrity.
- Transaction commit and rollback.
- Normalized reference-data reuse.
- Status-history persistence and ordering.
- Archive and restore persistence.
- Application data persistence across sessions.

### Flask Application Testing

Flask application tests verify application behavior through Flask's test
facilities without requiring a real browser.

Coverage may include:

- Route behavior.
- Form submission and processing.
- Validation responses.
- Successful and unsuccessful application operations.
- Search, filtering, sorting, and pagination behavior where browser execution
  adds little additional value.

### External UI Testing

Selenium tests verify critical workflows through a supported Chromium-based
browser.

UI automation shall focus on behavior for which browser-level verification
provides meaningful additional confidence.

Representative coverage includes:

- Recording an application.
- Displaying and editing application details.
- Duplicate-application warning and override.
- Application status changes and lifecycle display.
- Search and filtering.
- Archive and restore workflows.
- User-visible validation behavior.

Selenium coverage shall not duplicate every lower-level validation or boundary
test merely to increase UI test count.

### Manual and Exploratory Testing

Manual testing is a planned component of the Phase 1 quality strategy and is
not limited to behavior that cannot be automated.

Test coverage shall be selected based on the most appropriate testing method.
Not every requirement, scenario, or regression check needs to be automated.

Structured manual testing may be used when:

- Human observation or judgment provides meaningful value.
- A scenario is important but does not justify the cost or maintenance of
  automation.
- Behavior is changing frequently and automation would be premature.
- A scenario is executed infrequently.
- Exploratory investigation is more valuable than scripted automation.
- Visual presentation, readability, or usability is being evaluated.
- Independent manual verification provides useful additional confidence.

Manual testing may include documented test cases, targeted regression checks,
exploratory sessions, and ad hoc investigation.

Exploratory testing shall be used to investigate behavior beyond predetermined
test steps, including unexpected workflows, boundary conditions, and
interactions discovered during testing.

Manual coverage may later become automated when repetition, regression risk,
or execution cost provides sufficient value. Automation shall not be treated
as the default destination for every manual test.

## Test Selection and Coverage Philosophy

Test coverage shall be selected according to risk, behavior, repeatability,
and the value provided by each testing method and test level.

Automation is one component of the overall test strategy. Manual testing,
exploratory testing, and automated testing are complementary approaches rather
than stages in a progression toward complete automation.

A product requirement does not automatically require automated coverage or
equivalent coverage at every test level.

Tests shall normally be implemented at the lowest practical
level that provides reliable verification of the behavior.

Higher-level tests shall be added when they verify behavior or integration not
adequately demonstrated by lower-level coverage.

Examples include:

- Pure validation and normalization rules are primarily unit-test targets.
- Database constraints, transactions, and persistence behavior are primarily
  integration-test targets.
- Flask request processing and application workflow behavior are primarily
  application-test targets.
- Critical user workflows and browser-specific behavior are appropriate
  Selenium targets.
- Visual quality, usability, and unexpected interactions remain appropriate
  for manual and exploratory testing.

Critical behavior may intentionally receive coverage at multiple levels when
each level verifies a different risk.

Test selection shall favor:

- High-risk behavior.
- Important user workflows.
- Data-integrity rules.
- Boundary and negative conditions.
- Regression-prone behavior.
- Behavior that can be verified deterministically and maintained reliably.

Test selection shall avoid:

- Duplicating the same assertions across test levels without additional value.
- Automating behavior solely to increase test counts or coverage metrics.
- Using Selenium when a faster and more reliable lower-level test provides
  equivalent confidence.
- Creating application complexity solely to make a test easier to automate.

Code coverage and test counts may be used as supporting information but shall
not be treated as measures of product quality by themselves.

## Test Data and Isolation

Automated testing shall use controlled test data that is isolated from the
user's personal Job Search Hub data.

Automated tests shall not read, modify, or delete the user's personal Job Search Hub
database.

### Application Repository Tests

Unit, integration, and Flask application tests shall execute against isolated
test state.

Where database access is required, tests shall use a dedicated test database
that can be created, populated, and discarded independently of the user's
application database.

Tests shall establish the data required for their execution rather than depend
on records created by previous tests.

Tests shall be repeatable and shall not depend on execution order.

### External Automation Repository

Selenium automation shall execute against a dedicated test instance of Job Search Hub
using a dedicated test database.

The external automation environment shall not use the user's personal Job Search Hub
database.

Automated scenarios shall create or establish the data required for their
execution in a controlled and repeatable manner.

Test data shall be identifiable as test data and shall not contain real
personal job-search information unless specifically required for a controlled
manual test.

### Test Independence

Tests should be independent where practical.

A failed test shall not leave persistent state that causes unrelated subsequent
tests to fail.

Shared setup may be used when it improves execution efficiency without creating
hidden dependencies between tests.

Tests involving dates or times shall use controlled or explicitly established
values where required to produce deterministic results.

## Continuous Integration

Continuous integration shall provide repeatable automated verification of
changes to both Phase 1 repositories.

Each repository shall maintain its own CI workflow appropriate to its
responsibilities.

GitHub Actions shall be used for Phase 1 continuous integration.

### Application Repository CI

The `job-search-hub` repository CI workflow shall execute application-owned
automated tests.

The workflow shall include:

- Installing the required Python dependencies.
- Preparing an isolated test environment.
- Running unit tests.
- Running database and integration tests.
- Running Flask application tests.
- Reporting the overall test result.

The workflow shall run for changes pushed to the repository and for pull
requests where appropriate.

A failing required test shall cause the CI workflow to fail.

### External Automation Repository CI

The `job-search-hub-tests` repository shall maintain a separate CI workflow for
external Selenium automation.

The workflow shall include:

- Installing the automation dependencies.
- Obtaining or starting the required Job Search Hub application version.
- Preparing an isolated Job Search Hub test environment and test database.
- Starting the application.
- Starting the supported browser and WebDriver environment.
- Running the appropriate Selenium test suite.
- Reporting the overall test result.
- Preserving useful failure artifacts where practical.

Failure artifacts may include browser screenshots, logs, and test reports when
they provide useful diagnostic information.

### Cross-Repository Verification

The application and automation repositories shall remain independently
maintainable.

External automation shall verify a known version or revision of Job Search Hub so that
test results can be associated with the application version under test.

Cross-repository automation may be introduced when it provides sufficient
value, such as triggering an external regression suite for a significant Job
Hub change or release.

Phase 1 does not require complex cross-repository pipeline orchestration before
such a need exists.

### Continuous Delivery

Continuous delivery or deployment is not required for the initial Phase 1
implementation because Job Search Hub is initially intended to run locally.

Deployment automation may be introduced in a future phase if the application
gains a defined deployment target.

Infrastructure shall not be introduced solely for the purpose of demonstrating
continuous delivery.

## Traceability and Test Documentation

Testing shall maintain sufficient traceability to demonstrate how significant
Phase 1 requirements and risks are verified.

Traceability shall remain lightweight and useful rather than becoming a
documentation exercise.

### Automated Tests

Automated tests shall use descriptive names that communicate the behavior being
verified.

Where useful, automated tests or supporting documentation may reference the
applicable functional requirement or risk.

Traceability shall not require every automated test to duplicate requirement
text or embed excessive metadata in test code.

### Manual Tests

Structured manual tests shall be documented when repeatable manual verification
provides continuing value.

Manual test documentation shall identify:

- The behavior or objective being verified.
- Required preconditions or test data.
- The actions necessary to perform the test.
- The expected result.

Manual tests shall focus on behavior for which maintained manual coverage is
useful. They shall not duplicate automated coverage without a specific reason.

### Exploratory Testing

Exploratory testing does not require fully scripted test cases.

Significant exploratory sessions may record:

- The area or risk investigated.
- Important observations.
- Defects or questions discovered.
- Follow-up testing identified.

### Requirements Coverage

Phase 1 shall maintain a lightweight view of requirements coverage showing the
primary testing method or methods used for significant functional requirements.

A requirement may be covered by unit, integration, Flask application,
Selenium, structured manual, exploratory, or multiple forms of testing.

The purpose of requirements coverage is to identify meaningful gaps and explain
the testing approach, not to require identical coverage at every test level.

## Test Results, Failures, and Defects

Test execution shall produce sufficient information to determine what was
tested, whether the testing passed or failed, and what requires investigation.

### Automated Test Results

Automated test execution shall clearly identify:

- Tests executed.
- Tests passed.
- Tests failed.
- Tests skipped where applicable.
- Failure information sufficient to support investigation.

CI results shall remain associated with the repository revision that was
tested.

Additional reports or artifacts may be introduced when they provide useful
diagnostic or historical value. Reporting tools shall not be added solely to
increase project complexity.

### Failure Investigation

An automated test failure shall be investigated before being classified as a
product defect.

Investigation may determine that the failure represents:

- A product defect.
- A test defect.
- An environment or configuration problem.
- An expected product change requiring corresponding test maintenance.
- An intermittent or timing-related failure requiring further investigation.

Repeatedly rerunning a failed automated test until it passes shall not be used
as a substitute for understanding the cause of the failure.

Unreliable tests shall be corrected, redesigned, or removed from required
regression coverage when they cannot provide dependable results.

### Defects

Confirmed product defects shall contain sufficient information to reproduce and
understand the problem.

Defect documentation should include, where applicable:

- A concise description of the observed problem.
- The affected requirement or behavior.
- Preconditions and relevant test data.
- Steps or conditions required to reproduce the issue.
- Expected behavior.
- Actual behavior.
- Relevant evidence such as screenshots, logs, or automated test output.
- Severity or impact when useful for prioritization.

Defect documentation shall distinguish observed facts from investigation notes
or suspected causes.

### Regression Coverage

When a defect is corrected, the need for additional regression coverage shall
be evaluated.

Regression coverage may be implemented at any appropriate test level or through
structured manual testing.

A defect fix does not automatically require a new Selenium test. The regression
method shall be selected according to the risk of recurrence and the test level
that provides the most effective and maintainable verification.
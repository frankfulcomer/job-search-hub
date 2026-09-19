# Product Vision

## Background

Job-search information is currently maintained across spreadsheets, documents, communication systems, job sites, and supporting tools. As the amount of information and the relationships between that information increase, spreadsheet-based tracking becomes increasingly difficult to maintain and analyze.

At the same time, several related technical objectives have emerged:

- Develop practical Selenium experience against a realistic web application.
- Expand SQL skills through relational database design and application integration.
- Provide a persistent backend for Job Hunter and future job-discovery capabilities.
- Reduce reliance on AI for repeatable job-search decisions that can be expressed as application logic.
- Explore reporting and business intelligence using meaningful historical data.
- Maintain a portfolio project that demonstrates an AI-assisted engineering process transparently.

These objectives can be addressed through a single integrated system rather than through unrelated demonstration projects.

## Vision

Job Search Hub will provide a centralized system for capturing, organizing, evaluating, and analyzing job-search information.

The application will initially replace core spreadsheet-based tracking functions with a relational database and web interface. The system will evolve incrementally to support automated evaluation, external integrations, reporting, business intelligence, and selective use of AI for tasks that require interpretation rather than deterministic processing.

The application will serve both as a functional job-search tool and as a practical software engineering and quality assurance project.

## Core Principles

### System of Record

Job Search Hub will become the authoritative source for structured job-search information, including opportunities, applications, companies, contacts, activities, and outcomes.

### Incremental Development

Development will begin with a limited MVP. New capabilities will be introduced through planned releases rather than attempting to implement the complete long-term vision initially.

### Deterministic Logic Where Practical

Repeatable decisions should be implemented as testable application logic when sufficient rules and data exist.

Examples may include:

- Duplicate detection
- Compensation thresholds
- Location and commute evaluation
- Follow-up timing
- Application status management
- Opportunity scoring
- Configurable job-search preferences

AI should not remain responsible for decisions that can be reliably represented by deterministic logic.

### Selective AI Use

AI may be used where interpretation, ambiguity, or unstructured information makes deterministic processing impractical.

Potential uses include:

- Extracting structured information from job descriptions
- Interpreting unusual job requirements
- Identifying non-obvious experience matches
- Assisting with written communication
- Supporting requirements, design, implementation, review, and test development

AI responsibilities may decrease as stable patterns are identified and converted into application logic.

### Testability

The architecture should support testing at appropriate layers.

Expected testing includes:

- Unit testing of business and evaluation logic
- REST API testing
- Database and SQL validation
- Integration testing
- Selenium-based browser automation
- Exploratory testing

Browser automation should validate important end-to-end behavior rather than duplicate all lower-level testing.

### Historical Data

Important state changes and decisions should be preserved rather than overwritten when historical information has analytical value.

Examples include:

- Application status changes
- Job evaluations
- Recommendations
- Decision overrides
- Interviews
- Outcomes
- Job-search activities

Historical information will support reporting, business intelligence, and future evaluation of decision logic.

### Reporting and Analytics

The data model should support operational reporting and future business intelligence without compromising the transactional design of the application.

Potential analytical areas include:

- Application funnel performance
- Source effectiveness
- Employer response rates
- Interview conversion
- Skill demand
- Compensation trends
- Job-market characteristics
- Evaluation-engine performance
- Job-search activity over time

### Privacy by Design

Real job-search information is private.

Publicly shareable source code and documentation must not require exposure of personal job-search data, recruiter information, private communications, credentials, or other sensitive information.

Development and demonstration environments should support synthetic data suitable for testing, documentation, screenshots, and portfolio presentation.

### Transparent AI-Assisted Development

AI assistance is part of the engineering process and will be documented explicitly.

Documentation should distinguish among product direction, design assistance, implementation assistance, review, testing, and automated processes without overstating or understating any contributor's role.

AI-generated implementation should not be assumed correct. Functionality must be reviewed and tested before acceptance.

## Long-Term Direction

The long-term system may include:

1. A PostgreSQL-backed job-search system of record.
2. A web application and REST API for managing job-search information.
3. A configurable job-evaluation and recommendation engine.
4. Integration with Job Hunter and other job-discovery mechanisms.
5. SQL-based operational reporting.
6. Business intelligence dashboards and analysis.
7. Historical analysis of recommendations, decisions, and outcomes.
8. Selective AI-assisted interpretation of unstructured information.
9. Potential statistical or machine-learning models based on accumulated historical data.

These capabilities represent a direction rather than committed MVP scope. Each capability will be evaluated and planned before implementation.

## Success Criteria

The project will be successful if it:

- Becomes useful for managing an active job search.
- Reduces dependence on disconnected spreadsheets and manual tracking.
- Provides meaningful opportunities to exercise SQL, Selenium, API testing, and database testing.
- Supports integration with Job Hunter.
- Produces useful reporting and analytical capabilities.
- Moves suitable repeatable decisions from AI into testable application logic.
- Maintains private production data while supporting a public portfolio representation.
- Provides an accurate, documented record of the engineering decisions and lessons learned during development.
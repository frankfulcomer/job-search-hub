# Job Search Hub

Job Search Hub is a database-backed web application for managing the job-search lifecycle. The project is intended to consolidate information currently maintained across spreadsheets and other sources into a structured system of record.

The application will initially focus on managing job opportunities, applications, companies, contacts, and job-search activities. The architecture is intended to support future capabilities including automated job evaluation, Job Hunter integration, reporting, business intelligence, and AI-assisted processing.

## Project Objectives

- Replace increasingly complex spreadsheet-based job-search tracking with a relational data model.
- Provide a practical application for exercising SQL and database design skills.
- Provide a realistic web application for Selenium-based automated testing.
- Establish a central system of record that can integrate with Job Hunter and other job-discovery sources.
- Move repeatable job-search decisions into configurable application logic where practical.
- Preserve historical data for reporting, analysis, and evaluation of job-search strategies.
- Support future reporting and business intelligence capabilities.
- Provide a practical environment for exploring AI-assisted software development.

## Development Approach

The project will be developed incrementally, beginning with a minimum viable product (MVP). Later capabilities will be added through planned releases while maintaining a usable application at each major stage.

Development is being performed using an AI-assisted engineering workflow. Product requirements, architecture, implementation, testing, and documentation use different combinations of human direction and AI assistance. AI involvement will be documented as the project evolves rather than presented as independently authored work.

## Technology

The Phase 1 application is built with:

- Python
- Flask
- SQLite
- HTML/CSS
- Minimal JavaScript
- Pytest
- Git
- GitHub
- GitHub Actions

Selenium WebDriver browser automation is part of the Phase 1 quality engineering goal but lives in a separate, external test-automation repository rather than this one; see `docs/test-strategy.md` for the repository split.

Technology evolution beyond Phase 1 is tracked in `docs/roadmap.md` rather than duplicated here.

## Project Status

**Status:** Phase 1 (Functional MVP) implementation.

All Phase 1 functional and non-functional requirements defined in `docs/mvp-requirements.md` are implemented. The implementation is covered by an automated test suite verified through continuous integration on GitHub Actions; browser-level verification (NFR-004) is tracked separately in `docs/test-strategy.md` and is not yet automated.

See `docs/journal/` for the detailed implementation history and `docs/mvp-requirements.md` for the requirements themselves.

See the `docs/` directory for project planning and design documentation.

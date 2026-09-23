-- Insignificant text whitespace for Phase 1 normalization/blank checks is
-- space, tab, CR, and LF (see docs/decisions/0001-phase-1-sqlite-persistence-foundation.md).
-- SQLite's single-argument trim() only strips plain spaces, so every trim()
-- below passes this character set explicitly and consistently.

CREATE TABLE IF NOT EXISTS location (
    location_id INTEGER PRIMARY KEY,
    city TEXT,
    state_province TEXT,
    country TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (
        (city IS NOT NULL AND trim(city, char(32) || char(9) || char(13) || char(10)) <> '')
        OR (state_province IS NOT NULL AND trim(state_province, char(32) || char(9) || char(13) || char(10)) <> '')
        OR (country IS NOT NULL AND trim(country, char(32) || char(9) || char(13) || char(10)) <> '')
    )
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_location_normalized
    ON location (
        lower(trim(coalesce(city, ''), char(32) || char(9) || char(13) || char(10))),
        lower(trim(coalesce(state_province, ''), char(32) || char(9) || char(13) || char(10))),
        lower(trim(coalesce(country, ''), char(32) || char(9) || char(13) || char(10)))
    );

CREATE TRIGGER IF NOT EXISTS trg_location_updated_at
AFTER UPDATE ON location
FOR EACH ROW
WHEN NEW.city IS NOT OLD.city
    OR NEW.state_province IS NOT OLD.state_province
    OR NEW.country IS NOT OLD.country
BEGIN
    UPDATE location
       SET last_updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE location_id = NEW.location_id;
END;

CREATE TABLE IF NOT EXISTS company (
    company_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK (trim(name, char(32) || char(9) || char(13) || char(10)) <> ''),
    hq_location_id INTEGER REFERENCES location (location_id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_name_normalized
    ON company (lower(trim(name, char(32) || char(9) || char(13) || char(10))));

CREATE INDEX IF NOT EXISTS idx_company_hq_location_id ON company (hq_location_id);

CREATE TRIGGER IF NOT EXISTS trg_company_updated_at
AFTER UPDATE ON company
FOR EACH ROW
WHEN NEW.name IS NOT OLD.name
    OR NEW.hq_location_id IS NOT OLD.hq_location_id
BEGIN
    UPDATE company
       SET last_updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE company_id = NEW.company_id;
END;

CREATE TABLE IF NOT EXISTS source (
    source_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK (trim(name, char(32) || char(9) || char(13) || char(10)) <> ''),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_source_name_normalized
    ON source (lower(trim(name, char(32) || char(9) || char(13) || char(10))));

CREATE TRIGGER IF NOT EXISTS trg_source_updated_at
AFTER UPDATE ON source
FOR EACH ROW
WHEN NEW.name IS NOT OLD.name
BEGIN
    UPDATE source
       SET last_updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE source_id = NEW.source_id;
END;

CREATE TABLE IF NOT EXISTS status (
    status_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE CHECK (trim(name, char(32) || char(9) || char(13) || char(10)) <> ''),
    is_terminal INTEGER NOT NULL CHECK (is_terminal IN (0, 1)),
    display_order INTEGER NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

CREATE TRIGGER IF NOT EXISTS trg_status_updated_at
AFTER UPDATE ON status
FOR EACH ROW
WHEN NEW.name IS NOT OLD.name
    OR NEW.is_terminal IS NOT OLD.is_terminal
    OR NEW.display_order IS NOT OLD.display_order
BEGIN
    UPDATE status
       SET last_updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE status_id = NEW.status_id;
END;

CREATE TABLE IF NOT EXISTS application (
    application_id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES company (company_id),
    job_location_id INTEGER REFERENCES location (location_id),
    source_id INTEGER NOT NULL REFERENCES source (source_id),
    job_title TEXT NOT NULL CHECK (trim(job_title, char(32) || char(9) || char(13) || char(10)) <> ''),
    external_job_id TEXT,
    job_url TEXT,
    job_description TEXT,
    work_arrangement TEXT CHECK (work_arrangement IN ('ONSITE', 'HYBRID', 'REMOTE')),
    employment_type TEXT CHECK (employment_type IN ('FULL_TIME', 'PART_TIME', 'CONTRACT', 'TEMPORARY')),
    compensation_min REAL,
    compensation_max REAL,
    compensation_basis TEXT CHECK (compensation_basis IN ('ANNUAL', 'HOURLY')),
    application_date TEXT NOT NULL CHECK (
        application_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
    ),
    notes TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (
        compensation_min IS NULL OR compensation_max IS NULL
        OR compensation_min <= compensation_max
    ),
    CHECK (
        (compensation_min IS NULL AND compensation_max IS NULL)
        OR compensation_basis IS NOT NULL
    )
) STRICT;

CREATE INDEX IF NOT EXISTS idx_application_company_id ON application (company_id);
CREATE INDEX IF NOT EXISTS idx_application_source_id ON application (source_id);
CREATE INDEX IF NOT EXISTS idx_application_job_location_id ON application (job_location_id);

CREATE TRIGGER IF NOT EXISTS trg_application_updated_at
AFTER UPDATE ON application
FOR EACH ROW
WHEN NEW.company_id IS NOT OLD.company_id
    OR NEW.job_location_id IS NOT OLD.job_location_id
    OR NEW.source_id IS NOT OLD.source_id
    OR NEW.job_title IS NOT OLD.job_title
    OR NEW.external_job_id IS NOT OLD.external_job_id
    OR NEW.job_url IS NOT OLD.job_url
    OR NEW.job_description IS NOT OLD.job_description
    OR NEW.work_arrangement IS NOT OLD.work_arrangement
    OR NEW.employment_type IS NOT OLD.employment_type
    OR NEW.compensation_min IS NOT OLD.compensation_min
    OR NEW.compensation_max IS NOT OLD.compensation_max
    OR NEW.compensation_basis IS NOT OLD.compensation_basis
    OR NEW.application_date IS NOT OLD.application_date
    OR NEW.notes IS NOT OLD.notes
    OR NEW.archived_at IS NOT OLD.archived_at
BEGIN
    UPDATE application
       SET last_updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE application_id = NEW.application_id;
END;

CREATE TABLE IF NOT EXISTS application_status_history (
    application_status_history_id INTEGER PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES application (application_id),
    status_id INTEGER NOT NULL REFERENCES status (status_id),
    effective_at TEXT NOT NULL CHECK (
        effective_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]*'
    ),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (application_id, effective_at)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_ash_application_id ON application_status_history (application_id);
CREATE INDEX IF NOT EXISTS idx_ash_status_id ON application_status_history (status_id);

CREATE TRIGGER IF NOT EXISTS trg_ash_updated_at
AFTER UPDATE ON application_status_history
FOR EACH ROW
WHEN NEW.application_id IS NOT OLD.application_id
    OR NEW.status_id IS NOT OLD.status_id
    OR NEW.effective_at IS NOT OLD.effective_at
    OR NEW.notes IS NOT OLD.notes
BEGIN
    UPDATE application_status_history
       SET last_updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE application_status_history_id = NEW.application_status_history_id;
END;

INSERT OR IGNORE INTO status (name, is_terminal, display_order) VALUES
    ('APPLIED', 0, 1),
    ('SCREENING', 0, 2),
    ('INTERVIEWING', 0, 3),
    ('OFFER', 0, 4),
    ('ACCEPTED', 1, 5),
    ('REJECTED', 1, 6),
    ('WITHDRAWN', 1, 7),
    ('CLOSED', 1, 8);

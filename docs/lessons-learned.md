# Lessons Learned

This document records lessons observed during Phase 1 development, per
`development-process.md`'s guidance to record lessons after they occur
rather than predict them. Each entry reflects an actual incident found in
the project journal, not a general best practice asserted in the abstract.

## Timestamp and Timezone Handling

**A UTC-constructed default was compared against a locally-meaning value.**
`create_application`'s default `now` was originally constructed as
`datetime.now(timezone.utc)`, then compared via `now.date()` against
`application_date`, a value with no timezone of its own that originates
from the create form's `date.today()` default - which is local. The
comparison logic itself was correct; only the default's timezone frame was
wrong, and the mismatch was only visible for several hours daily in any
negative-UTC-offset timezone. The fix used `datetime.now().astimezone()`,
matching the frame the form itself uses to decide what "today" means. A
timestamp default's timezone frame needs to match what it will be compared
against, not simply be "aware" or "UTC" as a matter of general practice.

**Millisecond-precision persistence can make a stored timestamp appear
earlier than a higher-precision wall-clock bound.** A test asserted
`before <= archived_at <= after` using full microsecond-precision
`datetime.now()` captures, compared against a timestamp persisted at the
documented millisecond precision (ADR-0001). Both SQLite's `strftime('%f')`
default and the application's own `_format_timestamp` truncate (rather
than round) sub-millisecond precision, so a persisted value can legitimately
land up to ~1ms below the true write instant. This surfaced as a rare,
real CI flake rather than a bug: comparing a lower-precision persisted value
against higher-precision bounds requires tolerance matching the storage
layer's documented precision, not an assumption of exact equivalence.

## Input Validation and Boundary Handling

**Oversized integer inputs reached SQLite's 64-bit `INTEGER` range twice,
in two different routes.** An oversized `application_id` in a detail-view
URL, and later an oversized `job_location` filter value in the list view,
both raised an unhandled `OverflowError` (an unhandled 500) instead of
being treated as "no such row can exist." Both were fixed the same way -
catching `OverflowError` and treating it as a non-match - but the second
occurrence was a near-identical defect at a different entry point that the
first fix did not prevent. Any code path that converts user-controllable
input into a SQLite integer lookup is a candidate for this failure mode
and needs the same guard, not just the first place it was found.

**`urlparse` alone does not reject embedded whitespace.** Implementing
syntactic URL validation initially relied on `urlparse` plus a scheme
check, but `urlparse("http://exa mple.com")` parses "successfully" with
the space left inside the netloc. An explicit whitespace check was added
alongside `urlparse`, since library-provided parsing does not imply
strict format validation.

**SQLite's single-argument `trim()` only strips plain spaces.** Whitespace
normalization needed to treat space, tab, carriage return, and line feed
as insignificant (per `CHECK` constraints and uniqueness comparisons), but
SQLite's default `trim(x)` only strips spaces. Every blank-rejection
`CHECK` and every normalized-uniqueness index expression uses the
explicit two-argument `trim(x, y)` form with the same character set, so
the database-level blank check and the uniqueness comparison agree with
each other (documented in ADR-0001).

## Data Integrity Across Editing Workflows

**Form fields pre-filled from one entity's state became stale when the
form also allowed reassigning which entity they belonged to.** The
application-edit form pre-fills company headquarters fields from the
current company. Editing the Company field to a different company, while
leaving the pre-filled (now-stale) headquarters fields untouched, could
silently apply the *previous* company's headquarters to the newly-selected
company - overwriting a shared company's real headquarters without
adequate warning, or applying it outright to a new or unshared company
with no confirmation at all. The fix decouples reassignment from
headquarters editing entirely: whenever the edit changes which company an
application belongs to, submitted headquarters values are never applied
in that same request, regardless of whether the target company is new,
unshared, or shared. A form that both displays an entity's derived state
and allows changing which entity is selected needs to treat "reassign"
and "edit the newly-selected entity's own fields" as distinct operations,
not one combined submission.

## Test Reliability and Verification Discipline

**Hardcoded "today-relative" dates in tests silently expire.** A test
posted an application with a hardcoded date and no explicit status
effective time, relying on `create_application`'s "APPLIED status with
today's date" shortcut to supply one implicitly. The test passed for as
long as the hardcoded date matched the real calendar date, then began
failing - not because of a regression, but because the date had become
retrospective, correctly requiring an explicit effective time the test
never supplied. The fix replaced the hardcoded near-term date with a
fixed, clearly-past date and an explicit effective time, removing the
dependency on the real calendar entirely rather than substituting a
different date that would eventually fail the same way. Any test relying
on "is this date today" behavior needs either a fully fixed date or an
injected, controlled `now`, never a hardcoded date expected to remain
current indefinitely.

**Confirming a regression test is genuinely protective requires
reintroducing the defect it claims to catch.** Across FR-011, FR-010, and
the archived-timestamp flake, tests were verified by temporarily
reverting the fix (via monkeypatching a function to a no-op, or restoring
the pre-fix code in a disposable copy) and confirming the test then fails
for the expected reason, before restoring the fix. A test that merely
exercises the code path without failing under the specific defect it
claims to guard against provides false confidence; passing once is not
sufficient evidence that a test is protective.

## Version Control and Continuous Integration

**A single overly broad `.gitignore` pattern excluded a required source
file from version control for the project's entire history, undetected
until a genuinely fresh checkout was attempted.** The `.gitignore` entry
`*.sql`, intended to exclude database dumps, also matched
`src/job_hub/schema.sql` - a source file the application reads at
startup (`db.init_db`) and every test depends on. The file existed on
disk in every developer's working directory (since nothing ever deleted
it), so every local `pytest` run, and the entire test suite, passed
without issue for the whole project up to that point. The gap only
became visible once a CI workflow was added and GitHub Actions performed
an actual fresh `git clone`, which respects `.gitignore` and produced a
checkout missing the file entirely. A file present on disk is not
evidence it is tracked; only a genuinely fresh checkout (not a fresh
Python environment layered on the existing working directory) tests
whether the repository is actually self-contained.

**A fresh virtual environment is not equivalent to a fresh checkout.**
The CI workflow was initially validated locally by installing dependencies
into a disposable virtual environment and running the test suite - which
passed, and appeared to confirm the workflow would work on GitHub's
runners. This test isolated Python package state but not git-tracked-file
state, since it still pointed at the existing working directory
containing the untracked `schema.sql` file above; it could not have
caught that gap. Only cloning the repository into a separate directory
(mirroring what `actions/checkout` does) and running the same commands
there reproduced and confirmed the actual failure. Validating "will this
work in CI" requires reproducing what CI's checkout step actually does,
not just what its dependency-install step does.

## Documentation and Code Comment Accuracy

**Documentation and code comments drift out of sync with implementation
at multiple levels, not just one.** Three separate, unrelated instances
of this occurred during the project: a code comment on
`job_url_is_safe_link` described entry-time URL validation as
"intentionally deferred" immediately after that validation was
implemented, directly contradicting the code beside it; `README.md`
described the project as still in a pre-implementation "Planning" status
and listed a technology stack (FastAPI, PostgreSQL, SQLAlchemy) that was
never actually adopted, after most of Phase 1 had already shipped; and
`roadmap.md` continued to list status history and compensation tracking
as future Phase 2 work after both had been fully implemented as Phase 1
scope. None of these were caught by implementing new features correctly -
each was found only during a dedicated review or audit pass that reread
the affected document or comment against current behavior. Documentation
and comments require periodic, deliberate re-verification against the
current state of the code; correctness of new work does not imply the
surrounding documentation remains correct.

## Process

**Periodic, full-scope completion audits found real gaps that
incremental, feature-by-feature development did not.** Re-reading all
requirements, architecture, and test-strategy documentation fresh, and
cross-checking every claim against the current repository state rather
than trusting an accumulated mental model or a prior audit's conclusions,
repeatedly surfaced concrete, previously-unnoticed gaps: a fully
unimplemented requirement (FR-010's selection UI), validation gaps whose
absence was easy to miss incrementally (FR-011's URL and compensation-range
checks), an entirely missing CI workflow, and the documentation staleness
described above. Each audit pass treated the prior pass's conclusions as
a starting hypothesis to verify, not a fact to build on - which is what
allowed later passes to catch what earlier ones had missed, including
inaccuracies introduced by the audit-and-fix process itself.

## Privacy and Public Release Preparation

**A development transcript's captured tool output and terminal chrome
carried personal information that a review focused on prose content
would not have caught.** The verified canonical transcript's own text
never named its author, but eight of its lines - a captured Claude Code
status line and several `Write`/export tool-output lines - embedded the
account's real email address and absolute local filesystem paths that
exposed the operating-system username and home-directory layout. Both
categories were introduced automatically by the tools being transcribed,
not typed as prose by anyone the review would have recognized as
"personal information" from a narrative read. A transcript privacy
review needs to specifically inspect captured tool invocations, status
lines, and file paths, not only the surrounding narrative text, since
personal information can arrive through the environment rather than
through anything a person wrote.

**Sanitizing the canonical transcript did not, by itself, remove the
personal information the audit found, because unredacted duplicates of
the same content remained independently reachable in Git history.**
Four raw source transcripts, whose unique content had already been
fully incorporated into the verified canonical transcript per
`development-process.md`'s Transcript Preservation and Provenance
guidance, still existed as committed files earlier in history, carrying
the same real email address and absolute local paths, unredacted. A
privacy audit of a document that has a verified derivative is
incomplete until the documents it was derived from are checked
independently; a clean derivative does not imply its sources are clean.

**Removing a file from Git's current tree does not remove it from Git
history, and doing so via an ordinary new commit would not have closed
the actual exposure.** Because the four raw transcripts' unredacted
content would remain fully recoverable from the commits that introduced
them regardless of any later commit deleting the files, the only
remediation that matched the actual risk was rewriting history to drop
the four files from every commit that had ever contained them - which
necessarily changed the hash of every commit from the first
file-introducing commit onward (leaving two of those original commits
empty, preserved only for message and date continuity) and required a
force-push to replace the previously public history. Commit messages,
authorship, and dates were preserved unchanged through the rewrite, and
the sanitized canonical transcript's line count and unrelated content
were verified identical to the pre-sanitization version apart from the
eight corrected lines. Treating "delete the file" and "remove it from
history" as the same operation would have left the exposure in place.

**A force-push that rewrites a branch's history does not itself delete
the previously pushed objects from the hosting platform, or from any
existing local clone.** After the local history rewrite above was
force-pushed to `origin/main`, the pre-rewrite commits remained
independently retrievable: as unreferenced objects in GitHub's own
server-side storage (accessible by direct commit SHA even though no
branch or tag pointed at them anymore), and in this local clone's own
object store, reachable via `git reflog` even after local `main` was
reconciled to the sanitized remote. A version-control tag was a further,
separate gap of the same kind - a local tag continued pointing at a
pre-rewrite commit until it was explicitly replaced with the sanitized
remote tag. Closing a history-rewrite-based privacy remediation required
three further, independent actions beyond the rewrite and the push
itself: engaging the hosting platform to purge the unreferenced
server-side objects (confirmed only once representative pre-rewrite
commit SHAs returned HTTP 404 when requested directly), reconciling
every local branch to the sanitized remote, and reconciling every other
ref - including tags - that could still point at a pre-rewrite commit.
Rewriting history on one branch is not sufficient by itself; every place
a copy of the old objects could still be retrieved from - the hosting
platform's storage, any clone's local object store, and every ref in
every clone - has to be independently checked and reconciled.

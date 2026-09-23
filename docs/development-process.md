# Development Process

## Purpose

Job Search Hub uses an AI-assisted software engineering process in which product direction, design, implementation, review, and testing are treated as separate activities.

AI tools are used deliberately and transparently. Their output is treated as engineering input rather than assumed to be correct.

The development process is intended to maintain clear requirements, deliberate architectural decisions, traceable implementation, independent verification, and an accurate record of how the project evolves.

## Development Model

Development follows an incremental lifecycle:

1. Define the problem or capability.
2. Establish requirements and acceptance criteria.
3. Evaluate architectural and design implications.
4. Record significant decisions when appropriate.
5. Prepare implementation instructions.
6. Implement the approved design.
7. Review the implementation.
8. Execute appropriate automated and exploratory testing.
9. Resolve identified issues.
10. Update affected documentation.
11. Accept the change when the defined criteria are satisfied.

Implementation should not begin until the intended behavior is sufficiently understood.

## AI-Assisted Engineering

AI is an explicit part of the development process.

Different AI tools serve different purposes rather than relying on a single tool for all engineering activities.

### ChatGPT

ChatGPT primarily supports:

- Requirements analysis
- Architecture and design discussion
- Evaluation of technical alternatives
- Acceptance-criteria development
- Test strategy and test-design development
- Implementation planning
- Preparation of implementation instructions
- Code and implementation review assistance
- Documentation development
- Retrospective analysis and lessons learned

Recommendations produced during these activities remain subject to review before adoption.

### Claude

Claude primarily supports implementation activities, including:

- Application code
- Database integration
- Automated tests
- Refactoring
- Defect correction
- Implementation-level documentation

Implementation should follow approved requirements and design decisions.

Claude may identify technical concerns or propose alternatives during implementation. Significant changes to approved requirements or architecture should be reviewed before incorporation.

## Human Direction and Review

Human direction remains responsible for:

- Identifying the problem to be solved
- Providing domain knowledge
- Establishing priorities
- Selecting which capabilities should be developed
- Reviewing and approving requirements
- Reviewing architectural alternatives
- Approving significant design decisions
- Evaluating implementation behavior
- Performing exploratory testing
- Determining whether requirements have been satisfied
- Deciding when functionality is acceptable for release

AI-generated implementation is not considered validated solely because it compiles, executes, or passes AI-generated tests.

## AI-Assisted Change Control

Implementation proceeds from an explicitly scoped task, as described under Implementation Instructions. Implementation should not extend beyond that scope; additional work identified along the way should be reported rather than performed without separate authorization from human direction.

Routine, non-destructive, in-scope operations reasonably necessary to complete an authorized task may proceed without repeated confirmation - for example, reading or searching files, inspecting Git status, diffs, or history, running tests and other verification commands, comparing files, and other reversible local investigation. Confirmation should not be requested for individual routine commands once the overall task is authorized.

An implemented change is verified before being considered ready for review. Verification should include both targeted verification of the specific behavior changed and appropriate broader regression verification, such as the complete automated test suite, before a fix or change is considered complete. See Testing and Verification for expected test layers.

Independent review should occur before a verified change is committed, whenever practical. Review should be performed fresh against the actual change and applicable governing documentation - including requirements, architecture, and ADRs - independently deriving conclusions rather than relying on the implementing agent's own summary or prior narrative. Review findings should be reported by severity and addressed or deliberately deferred; findings should not be left unresolved without a documented decision, should remain traceable rather than disappearing across later review iterations, and unrequested fixes should not be applied unilaterally, even for issues found during review.

Human approval remains required at meaningful control boundaries, regardless of how routine the operations leading up to them were:

- Expanding beyond the authorized task scope.
- Committing changes.
- Pushing changes.
- Initiating continuous integration or other externally consequential operations not already explicitly authorized.
- Destructive Git operations, including force-push, history rewriting, hard resets, and discarding uncommitted work.
- Deleting, replacing, or intentionally discarding source or project records.
- Proceeding with unrelated corrective work discovered during an authorized task.

Destructive Git operations and record deletion or replacement are not performed as an incidental part of another task, even when the surrounding work is otherwise authorized. Completing or being authorized for one stage does not imply authorization for the next. Work stops at the boundary of what was explicitly requested; status is reported and further direction is awaited, rather than proceeding on an inferred next step.

Unexpected test or CI failures are investigated before being assumed to result from the current change; investigation should distinguish an introduced regression from a pre-existing defect, a flaky test, an environmental issue, a representation or precision issue, or another cause. The evidence, likely root cause, impact, and recommended disposition are reported for a decision rather than corrected without authorization, unless correcting the failure is itself the authorized task - authorization to investigate a failure does not by itself authorize correcting it. If correction would require work outside the authorized scope, work stops for human direction. Following an authorized correction, appropriate targeted and broader verification is re-run.

Each unit of work concludes with a journal entry recording what was implemented, verified, found, and deferred. See Documentation for what the project journal should preserve.

## Implementation Instructions

Implementation work should be based on defined requirements and acceptance criteria.

Implementation instructions should provide sufficient context to reduce unintended design decisions during coding. Where appropriate, instructions should identify:

- Required behavior
- Acceptance criteria
- Relevant architecture
- Constraints
- Expected tests
- Files or components that may be affected
- Areas that should not be changed
- Documentation that may require updates

Large changes should be divided into reviewable increments.

## Testing and Verification

Testing should occur at the lowest practical layer capable of verifying the behavior.

Expected test layers include:

- Unit tests
- API tests
- Database and SQL tests
- Integration tests
- Selenium browser tests
- Exploratory testing

Selenium tests should focus on important user workflows and browser behavior rather than duplicating exhaustive business-logic testing that can be performed more efficiently at lower layers.

Automated tests generated with implementation code require review. Passing tests do not independently establish that the underlying requirements are correct or complete.

When practical, a regression test's effectiveness should be demonstrated by recreating or deliberately introducing the defect condition it targets and confirming that the test detects it. See [lessons-learned.md](lessons-learned.md) for project history illustrating this practice, offered as supporting evidence rather than as a substitute for demonstrating a specific test's effectiveness.

## Source Control

Git provides the historical record of project development.

Changes should be committed in logical increments representing meaningful project changes rather than arbitrary development checkpoints.

Committing, pushing, and verifying continuous integration are separate, individually authorized steps in the change-control sequence described under AI-Assisted Change Control. A successful local commit does not by itself complete a change; where pushing and CI verification have been requested, the change remains incomplete until those steps have also been performed and confirmed. See [the test strategy](test-strategy.md) for continuous integration requirements.

Each commit message should be explicit and deliberate, accurately describing the completed unit of work. Commit messages should be specified and reviewed by human direction before the commit is created, rather than independently invented by an AI coding assistant - see AI-Assisted Change Control for the general authorization principle this reflects. Commit messages should be concise, written in the imperative mood, and describe the purpose of the change rather than listing the files touched or the editing mechanics involved.

The initial repository will remain private while the MVP is developed and reviewed.

Before public release, the repository will undergo a specific review for:

- Personal information
- Credentials and secrets
- Private job-search information
- Database contents and exports
- Logs
- Screenshots
- Test data
- File metadata
- Documentation content
- Git history

The stable public release will be maintained on the `main` branch and identified with a version tag.

Development may continue through feature or development branches after the repository becomes public.

## Documentation

Project documentation uses Markdown and follows a professional, impersonal technical writing style.

Documentation should:

- Be direct and factual.
- Avoid unnecessary promotional language.
- Avoid personal names and first-person references.
- Distinguish confirmed decisions from proposals and future possibilities.
- Explain significant decisions and their rationale.
- Preserve superseded decisions when they provide useful historical context.
- Record lessons after they are observed rather than predicting them.
- Describe AI involvement accurately without overstating or understating contributions.

Significant architectural decisions should be captured through Architecture Decision Records (ADRs).

The project journal should preserve important developments, questions, changes in direction, and the context in which decisions were made, with enough evidence to reconstruct what occurred, why consequential decisions were made, and how conclusions were verified.

## Transcript Preservation and Provenance

AI-assisted development transcripts are project records that complement the journal and Git history rather than replace either. Journal entries should complement, not attempt to reproduce, raw development transcripts.

Transcript exports are stored under `docs/transcripts/`. Source transcript content is preserved verbatim: a source transcript is not rewritten, summarized, cleaned up, or otherwise modified, and no substantive material is silently omitted. Transcripts should be captured at meaningful project or session boundaries and before transcript context could otherwise be lost.

A continuing session may be exported more than once, and later exports may overlap earlier ones rather than superseding them outright; the newest export should not be assumed to contain all earlier material.

When overlapping transcripts are consolidated into a single canonical transcript, overlap boundaries are determined explicitly from the actual source files - not assumed from filenames, timestamps, or prior summaries - every unique substantive portion is preserved, chronological order is preserved, and the latest rendition of a portion is preferred only where the same material is demonstrably duplicated and no substantive information would be lost. A consolidated transcript may be designated canonical only once its overlap boundaries, chronological continuity, unique-content coverage, exclusions, and fidelity to every contributing source have been independently verified. Provenance is preserved sufficient to identify every source transcript contributing to a canonical transcript, how overlapping regions were resolved, and any source material intentionally excluded and why.

Source transcripts remain provenance records after a verified canonical transcript exists and are not deleted, replaced, or discarded merely because a canonical transcript has been created; doing so is the same kind of consequential action described under AI-Assisted Change Control and requires the same explicit human authorization. Once a canonical transcript has been independently verified against its contributing sources, that verification result and its provenance are preserved rather than unnecessarily repeated; subsequent work may rely on the verified canonical record unless evidence is discovered that calls its integrity or completeness into question.

### Highlights

A highlights document may be derived from a verified canonical transcript to make the development effort easier for a human reviewer to understand. Highlights are a secondary artifact and never replace the canonical transcript, source transcripts, journal, requirements, architecture/ADR documentation, tests, or Git history.

Highlights should emphasize significant requirements decisions, architecture and design decisions, QA reasoning, test-design decisions, defects and findings, independent reviews, verification evidence, CI incidents, root-cause investigations, corrections, lessons learned, important changes in direction, and meaningful human/AI decision points, and should accurately distinguish human decisions and direction from AI implementation, investigation, recommendations, and verification. Highlights do not manufacture a cleaner development story by omitting meaningful failures, corrections, disagreements, rework, or discoveries; those are part of the engineering record and may themselves be significant highlights.

## Definition of Done

A change may be considered complete when applicable criteria have been satisfied:

- Requirements and acceptance criteria are met.
- Implementation has been reviewed.
- Appropriate automated tests pass.
- Required exploratory testing has been completed.
- Known defects have been evaluated.
- Relevant documentation has been updated.
- Architectural decisions have been recorded when necessary.
- Privacy implications have been reviewed.
- No unintended personal or sensitive information has been introduced.
- The application remains in a usable state.

Not every change requires every activity. The level of process should remain proportional to the risk and complexity of the change.

## Process Evolution

This development process is expected to evolve as practical experience is gained.

Changes to the process should be documented when they represent a meaningful change in how the project is designed, implemented, tested, or released.

Lessons learned during development should be used to improve subsequent work.
import math
import sqlite3
from datetime import date, datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from job_hub import db
from job_hub.applications import (
    COMPENSATION_BASES,
    DEFAULT_INITIAL_STATUS,
    EMPLOYMENT_TYPES,
    RECORD_STATES,
    WORK_ARRANGEMENTS,
    LastRemainingStatusHistoryRecordError,
    LocationInput,
    SharedHeadquartersChangeRequiresConfirmation,
    ValidationError,
    archive_application,
    change_application_status,
    correct_status_history,
    create_application,
    delete_status_history,
    edit_application,
    get_application_detail,
    list_applications,
    restore_application,
)

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    return render_template("home.html")


def _blank_to_none(value):
    value = (value or "").strip()
    return value or None


def _parse_application_date(value):
    value = (value or "").strip()
    if not value:
        raise ValidationError("application_date", "is required")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError("application_date", "must be a valid date") from None


def _parse_effective_at(value, field="initial_status_effective_at"):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise ValidationError(field, "must be a valid date and time") from None


def _parse_compensation(field, value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError:
        raise ValidationError(field, "must be a number") from None
    if not math.isfinite(parsed):
        raise ValidationError(field, "must be a number") from None
    return parsed


def _location_from_form(form, prefix):
    return LocationInput(
        city=form.get(f"{prefix}_city"),
        state_province=form.get(f"{prefix}_state_province"),
        country=form.get(f"{prefix}_country"),
    )


def _parse_common_application_fields(form):
    return {
        "company_name": form.get("company_name", ""),
        "job_title": form.get("job_title", ""),
        "application_date": _parse_application_date(form.get("application_date")),
        "source_name": form.get("source_name", ""),
        "job_location": _location_from_form(form, "job_location"),
        "company_hq_location": _location_from_form(form, "company_hq"),
        "job_description": _blank_to_none(form.get("job_description")),
        "job_url": _blank_to_none(form.get("job_url")),
        "external_job_id": _blank_to_none(form.get("external_job_id")),
        "work_arrangement": _blank_to_none(form.get("work_arrangement")),
        "employment_type": _blank_to_none(form.get("employment_type")),
        "compensation_min": _parse_compensation(
            "compensation_min", form.get("compensation_min")
        ),
        "compensation_max": _parse_compensation(
            "compensation_max", form.get("compensation_max")
        ),
        "compensation_basis": _blank_to_none(form.get("compensation_basis")),
        "notes": _blank_to_none(form.get("notes")),
    }


def _parse_application_form(form):
    fields = _parse_common_application_fields(form)
    fields["initial_status_name"] = (
        form.get("initial_status_name") or DEFAULT_INITIAL_STATUS
    )
    fields["initial_status_effective_at"] = _parse_effective_at(
        form.get("initial_status_effective_at")
    )
    return fields


def _parse_edit_application_form(form):
    fields = _parse_common_application_fields(form)
    fields["confirm_shared_headquarters_change"] = (
        form.get("confirm_shared_headquarters_change") == "1"
    )
    return fields


def _edit_form_data_from_detail(detail):
    def as_text(value):
        return value if value is not None else ""

    return {
        "company_name": detail.company_name,
        "job_title": detail.job_title,
        "application_date": detail.application_date,
        "source_name": detail.source_name,
        "job_location_city": as_text(detail.job_location_city),
        "job_location_state_province": as_text(detail.job_location_state_province),
        "job_location_country": as_text(detail.job_location_country),
        "company_hq_city": as_text(detail.company_hq_city),
        "company_hq_state_province": as_text(detail.company_hq_state_province),
        "company_hq_country": as_text(detail.company_hq_country),
        "work_arrangement": as_text(detail.work_arrangement),
        "employment_type": as_text(detail.employment_type),
        "compensation_min": as_text(detail.compensation_min_display),
        "compensation_max": as_text(detail.compensation_max_display),
        "compensation_basis": as_text(detail.compensation_basis),
        "external_job_id": as_text(detail.external_job_id),
        "job_url": as_text(detail.job_url),
        "job_description": as_text(detail.job_description),
        "notes": as_text(detail.notes),
    }


def _status_options(connection):
    return connection.execute(
        "SELECT name FROM status ORDER BY display_order"
    ).fetchall()


def _find_history_entry(detail, history_id):
    for entry in detail.status_history:
        if entry.application_status_history_id == history_id:
            return entry
    return None


@main_bp.route("/applications/new", methods=["GET", "POST"])
def new_application():
    connection = db.get_db()
    error = None
    error_field = None
    form_data = {}

    if request.method == "POST":
        form_data = request.form
        try:
            fields = _parse_application_form(form_data)
            result = create_application(connection, **fields)
            flash(
                f"Created application for {fields['job_title'].strip()} at "
                f"{fields['company_name'].strip()} (#{result.application_id}).",
                "success",
            )
            return redirect(url_for("main.application_list"))
        except ValidationError as exc:
            error = str(exc)
            error_field = exc.field
        except sqlite3.IntegrityError:
            error = (
                "The application could not be saved because it conflicts with "
                "existing data. Please review the values and try again."
            )

    return render_template(
        "applications/new.html",
        error=error,
        error_field=error_field,
        form_data=form_data,
        status_options=_status_options(connection),
        work_arrangements=WORK_ARRANGEMENTS,
        employment_types=EMPLOYMENT_TYPES,
        compensation_bases=COMPENSATION_BASES,
        today=date.today().isoformat(),
    )


@main_bp.route("/applications")
def application_list():
    connection = db.get_db()

    sort = request.args.get("sort", "")
    direction = request.args.get("dir", "")
    record_state = request.args.get("state", "")
    try:
        page = int(request.args.get("page", 1))
    except ValueError:
        page = 1

    result = list_applications(
        connection,
        sort=sort,
        direction=direction,
        page=page,
        record_state=record_state,
    )

    return render_template(
        "applications/list.html", result=result, record_states=RECORD_STATES
    )


@main_bp.route("/applications/<int:application_id>")
def application_detail(application_id):
    connection = db.get_db()
    try:
        detail = get_application_detail(connection, application_id)
    except OverflowError:
        # SQLite INTEGER bind parameters are 64-bit; an out-of-range id in
        # the URL can't match a row either way, so treat it as not found.
        detail = None
    if detail is None:
        abort(404)

    return render_template("applications/detail.html", detail=detail)


@main_bp.route("/applications/<int:application_id>/edit", methods=["GET", "POST"])
def application_edit(application_id):
    connection = db.get_db()
    try:
        detail = get_application_detail(connection, application_id)
    except OverflowError:
        detail = None
    if detail is None:
        abort(404)

    error = None
    error_field = None
    confirmation = None
    form_data = _edit_form_data_from_detail(detail)

    if request.method == "POST":
        form_data = request.form
        try:
            fields = _parse_edit_application_form(form_data)
            result = edit_application(connection, application_id, **fields)
            flash(
                f"Updated application for {fields['job_title'].strip()} at "
                f"{fields['company_name'].strip()}.",
                "success",
            )
            if result.company_reassigned:
                flash(
                    "Company changed. Any headquarters submitted with this edit "
                    "was not applied - edit the application again if you'd like "
                    "to update the new company's headquarters.",
                    "info",
                )
            return redirect(
                url_for("main.application_detail", application_id=application_id)
            )
        except SharedHeadquartersChangeRequiresConfirmation as exc:
            confirmation = exc
        except ValidationError as exc:
            error = str(exc)
            error_field = exc.field
        except sqlite3.IntegrityError:
            error = (
                "The application could not be saved because it conflicts with "
                "existing data. Please review the values and try again."
            )

    return render_template(
        "applications/edit.html",
        application_id=application_id,
        error=error,
        error_field=error_field,
        confirmation=confirmation,
        form_data=form_data,
        work_arrangements=WORK_ARRANGEMENTS,
        employment_types=EMPLOYMENT_TYPES,
        compensation_bases=COMPENSATION_BASES,
    )


@main_bp.route("/applications/<int:application_id>/status", methods=["GET", "POST"])
def application_status_change(application_id):
    connection = db.get_db()
    try:
        detail = get_application_detail(connection, application_id)
    except OverflowError:
        detail = None
    if detail is None:
        abort(404)

    error = None
    error_field = None
    form_data = {}

    if request.method == "POST":
        form_data = request.form
        try:
            status_name = form_data.get("status_name", "")
            effective_at = _parse_effective_at(
                form_data.get("effective_at"), field="effective_at"
            )
            notes = _blank_to_none(form_data.get("notes"))
            change_application_status(
                connection,
                application_id,
                status_name=status_name,
                effective_at=effective_at,
                notes=notes,
            )
            flash(
                f"Recorded status change to {status_name.strip()} for "
                f"{detail.job_title} at {detail.company_name}.",
                "success",
            )
            return redirect(
                url_for("main.application_detail", application_id=application_id)
            )
        except ValidationError as exc:
            error = str(exc)
            error_field = exc.field
        except sqlite3.IntegrityError:
            error = (
                "This status change could not be saved because another status "
                "change already has the same effective date and time. Please "
                "choose a different date and time."
            )

    return render_template(
        "applications/status.html",
        application_id=application_id,
        detail=detail,
        error=error,
        error_field=error_field,
        form_data=form_data,
        status_options=_status_options(connection),
    )


@main_bp.route(
    "/applications/<int:application_id>/status/<int:history_id>/edit",
    methods=["GET", "POST"],
)
def application_status_correct(application_id, history_id):
    connection = db.get_db()
    try:
        detail = get_application_detail(connection, application_id)
    except OverflowError:
        detail = None
    if detail is None:
        abort(404)

    entry = _find_history_entry(detail, history_id)
    if entry is None:
        abort(404)

    error = None
    error_field = None
    form_data = {
        "status_name": entry.status_name,
        "effective_at": entry.effective_at[:16],
        "notes": entry.notes or "",
    }

    if request.method == "POST":
        form_data = request.form
        try:
            status_name = form_data.get("status_name", "")
            effective_at = _parse_effective_at(
                form_data.get("effective_at"), field="effective_at"
            )
            notes = _blank_to_none(form_data.get("notes"))
            correct_status_history(
                connection,
                application_id,
                history_id,
                status_name=status_name,
                effective_at=effective_at,
                notes=notes,
            )
            flash(
                f"Corrected status history entry to {status_name.strip()} for "
                f"{detail.job_title} at {detail.company_name}.",
                "success",
            )
            return redirect(
                url_for("main.application_detail", application_id=application_id)
            )
        except ValidationError as exc:
            error = str(exc)
            error_field = exc.field
        except sqlite3.IntegrityError:
            error = (
                "This correction could not be saved because another status "
                "change already has the same effective date and time. Please "
                "choose a different date and time."
            )

    return render_template(
        "applications/status_correct.html",
        application_id=application_id,
        history_id=history_id,
        detail=detail,
        error=error,
        error_field=error_field,
        form_data=form_data,
        status_options=_status_options(connection),
    )


@main_bp.route(
    "/applications/<int:application_id>/status/<int:history_id>/delete",
    methods=["GET", "POST"],
)
def application_status_delete(application_id, history_id):
    connection = db.get_db()
    try:
        detail = get_application_detail(connection, application_id)
    except OverflowError:
        detail = None
    if detail is None:
        abort(404)

    entry = _find_history_entry(detail, history_id)
    if entry is None:
        abort(404)

    is_only_entry = len(detail.status_history) <= 1
    error = None

    if request.method == "POST":
        try:
            delete_status_history(connection, application_id, history_id)
            flash(
                f"Deleted status history entry ({entry.status_name}) for "
                f"{detail.job_title} at {detail.company_name}.",
                "success",
            )
            return redirect(
                url_for("main.application_detail", application_id=application_id)
            )
        except LastRemainingStatusHistoryRecordError:
            error = (
                "This is the only status history record for this application "
                "and cannot be deleted."
            )

    return render_template(
        "applications/status_delete.html",
        application_id=application_id,
        history_id=history_id,
        detail=detail,
        entry=entry,
        is_only_entry=is_only_entry,
        error=error,
    )


@main_bp.route("/applications/<int:application_id>/archive", methods=["GET", "POST"])
def application_archive(application_id):
    connection = db.get_db()
    try:
        detail = get_application_detail(connection, application_id)
    except OverflowError:
        detail = None
    if detail is None:
        abort(404)

    if request.method == "POST":
        archive_application(connection, application_id)
        flash(
            f"Archived application for {detail.job_title} at "
            f"{detail.company_name}.",
            "success",
        )
        return redirect(
            url_for("main.application_detail", application_id=application_id)
        )

    return render_template(
        "applications/archive_confirm.html",
        application_id=application_id,
        detail=detail,
    )


@main_bp.route("/applications/<int:application_id>/restore", methods=["POST"])
def application_restore(application_id):
    connection = db.get_db()
    try:
        detail = get_application_detail(connection, application_id)
    except OverflowError:
        detail = None
    if detail is None:
        abort(404)

    restore_application(connection, application_id)
    flash(
        f"Restored application for {detail.job_title} at {detail.company_name}.",
        "success",
    )
    return redirect(url_for("main.application_detail", application_id=application_id))

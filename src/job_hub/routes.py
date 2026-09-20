import math
import sqlite3
from datetime import date, datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from job_hub import db
from job_hub.applications import (
    COMPENSATION_BASES,
    DEFAULT_INITIAL_STATUS,
    EMPLOYMENT_TYPES,
    WORK_ARRANGEMENTS,
    LocationInput,
    ValidationError,
    create_application,
    get_application_detail,
    list_applications,
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


def _parse_effective_at(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise ValidationError(
            "initial_status_effective_at", "must be a valid date and time"
        ) from None


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


def _parse_application_form(form):
    return {
        "company_name": form.get("company_name", ""),
        "job_title": form.get("job_title", ""),
        "application_date": _parse_application_date(form.get("application_date")),
        "source_name": form.get("source_name", ""),
        "initial_status_name": form.get("initial_status_name")
        or DEFAULT_INITIAL_STATUS,
        "initial_status_effective_at": _parse_effective_at(
            form.get("initial_status_effective_at")
        ),
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


def _status_options(connection):
    return connection.execute(
        "SELECT name FROM status ORDER BY display_order"
    ).fetchall()


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
    try:
        page = int(request.args.get("page", 1))
    except ValueError:
        page = 1

    result = list_applications(connection, sort=sort, direction=direction, page=page)

    return render_template("applications/list.html", result=result)


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

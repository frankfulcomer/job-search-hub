import sqlite3
from pathlib import Path

import click
from flask import current_app, g

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(database):
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])

    return g.db


def close_db(e=None):
    connection = g.pop("db", None)

    if connection is not None:
        connection.close()


def init_db(connection):
    connection.executescript(SCHEMA_PATH.read_text())
    connection.commit()


@click.command("init-db")
def init_db_command():
    init_db(get_db())
    click.echo("Initialized the database.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)

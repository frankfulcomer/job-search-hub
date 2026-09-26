import os

from flask import Flask

from job_hub.config import Config


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=os.environ.get(
            "JOB_HUB_DATABASE",
            os.path.join(app.instance_path, "job_hub.sqlite3"),
        ),
    )
    app.config.from_object(config or Config)

    os.makedirs(app.instance_path, exist_ok=True)

    from job_hub import db

    db.init_app(app)
    with app.app_context():
        db.init_db(db.get_db())

    from job_hub.routes import main_bp

    app.register_blueprint(main_bp)

    return app

from flask import Flask

from job_hub.config import Config


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(config or Config)

    from job_hub.routes import main_bp

    app.register_blueprint(main_bp)

    return app

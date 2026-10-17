from flask import Blueprint, jsonify
from app.db import check_connection

db_health_bp = Blueprint("db_health", __name__)


@db_health_bp.route("/api/db-health", methods=["GET"])
def db_health_check():
    result = check_connection()
    status_code = 200 if result["connected"] else 500
    return jsonify(result), status_code

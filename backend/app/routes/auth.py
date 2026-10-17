import re

from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from mysql.connector import Error as MySQLError
from mysql.connector.errors import IntegrityError

from app.models.user_model import (
    create_user, get_user_by_email, get_user_by_id, set_user_allergies,
)

auth_bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8


@auth_bp.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    password = data.get("password") or ""

    if not name or not email or not password:
        return jsonify({"error": "name, email and password are required"}), 400
    if len(name) > 150 or len(email) > 150 or len(phone) > 20:
        return jsonify({"error": "name, email or phone is too long"}), 400
    if not EMAIL_RE.match(email):
        return jsonify({"error": "invalid email format"}), 400
    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({"error": f"password must be at least {MIN_PASSWORD_LENGTH} characters"}), 400

    if get_user_by_email(email):
        return jsonify({"error": "an account with this email already exists"}), 409

    password_hash = generate_password_hash(password)

    try:
        user_id = create_user(name, email, phone, password_hash)
    except IntegrityError:
        # covers the rare race where two requests register the same email at once
        return jsonify({"error": "an account with this email already exists"}), 409
    except MySQLError as e:
        return jsonify({"error": "database error", "details": str(e)}), 500

    return jsonify({"message": "registration successful", "user_id": user_id}), 201


@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    try:
        user = get_user_by_email(email)
    except MySQLError as e:
        return jsonify({"error": "database error", "details": str(e)}), 500

    if not user or not check_password_hash(user["password"], password):
        # deliberately identical message for "no such user" and "wrong password"
        # so a caller can't use this endpoint to discover which emails are registered
        return jsonify({"error": "invalid email or password"}), 401

    token = create_access_token(identity=str(user["user_id"]))
    return jsonify({
        "message": "login successful",
        "access_token": token,
        "user": {
            "user_id": user["user_id"],
            "name": user["name"],
            "email": user["email"],
            "phone": user["phone"],
        },
    }), 200


@auth_bp.route("/api/auth/me", methods=["GET"])
@jwt_required()
def me():
    user_id = get_jwt_identity()
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({"error": "user not found"}), 404
    return jsonify({"user": user}), 200


MAX_ALLERGIES = 20
MAX_ALLERGY_LENGTH = 60
_ALLERGY_SPLIT_RE = re.compile(r"[,;\n]+")


def normalize_allergies(raw):
    """
    Accepts free text ("penicillin, sulfa") or a list, and returns a clean,
    de-duplicated list. Bounded, because this is user-typed input that ends
    up compared against every medicine on every prescription.
    """
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else _ALLERGY_SPLIT_RE.split(str(raw))
    cleaned, seen = [], set()
    for item in items:
        text = re.sub(r"\s+", " ", str(item)).strip()[:MAX_ALLERGY_LENGTH]
        if len(text) < 2 or text.lower() in seen:
            continue
        seen.add(text.lower())
        cleaned.append(text)
    return cleaned[:MAX_ALLERGIES]


@auth_bp.route("/api/auth/me/allergies", methods=["PUT"])
@jwt_required()
def update_allergies():
    """
    Saves the user's self-declared allergies, then refreshes the safety
    analysis of their existing prescriptions so no stored finding still
    claims "no allergy information on file".
    """
    user_id = get_jwt_identity()
    if not get_user_by_id(user_id):
        return jsonify({"error": "user not found"}), 404

    data = request.get_json(silent=True) or {}
    if "allergies" not in data:
        return jsonify({"error": "allergies is required (text or list)"}), 400

    allergies = normalize_allergies(data.get("allergies"))
    set_user_allergies(user_id, allergies)

    from app.services.clinical_decision_service import refresh_user_analyses
    refreshed = refresh_user_analyses(user_id)

    return jsonify({"allergies": allergies, "prescriptions_refreshed": refreshed}), 200

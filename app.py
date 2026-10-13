import os

import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, jsonify, request
from flask_cors import CORS

# Path to the service account key (keep this file out of git)
CRED_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")

firebase_admin.initialize_app(credentials.Certificate(CRED_PATH))
db = firestore.client()

app = Flask(__name__)
CORS(app)

REQUIRED_FIELDS = ["borrowerId", "loanAmount", "propertyValue"]


def serialise(doc):
    """Turn a Firestore document into a JSON-friendly dict."""
    data = doc.to_dict()
    data["id"] = doc.id
    for key, value in data.items():
        if hasattr(value, "isoformat"):
            data[key] = value.isoformat()
    return data


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/applications")
def create_application():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body must be JSON"}), 400

    missing = [f for f in REQUIRED_FIELDS if f not in body]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    application = {
        "borrowerId": body["borrowerId"],
        "loanAmount": body["loanAmount"],
        "propertyValue": body["propertyValue"],
        "status": "Applied",
        "createdAt": firestore.SERVER_TIMESTAMP,
    }
    _, ref = db.collection("applications").add(application)
    return jsonify({"id": ref.id, "status": "Applied"}), 201


@app.get("/applications")
def list_applications():
    docs = db.collection("applications").stream()
    return jsonify([serialise(d) for d in docs])


@app.get("/applications/<app_id>")
def get_application(app_id):
    doc = db.collection("applications").document(app_id).get()
    if not doc.exists:
        return jsonify({"error": "Application not found"}), 404
    return jsonify(serialise(doc))


if __name__ == "__main__":
    app.run(debug=True, port=5000)

"""
Tests the PUBLISHED Firestore security rules against the real project.

It signs in as the three test accounts (borrower, broker, underwriter) using the
Firebase Auth REST API, then sends Firestore REST requests with each user's ID
token, so the rules are enforced exactly as they are for the Mobile and Web apps.
Test data is seeded with the Admin SDK (which bypasses rules) and removed at the end.

Setup:
    pip install requests firebase-admin
    serviceAccountKey.json in the same folder (or GOOGLE_APPLICATION_CREDENTIALS set)

Run:
    python test_rules.py

You will be asked for the web apiKey (Firebase console > Settings > General >
Your apps > AL-Web > apiKey) and the password of the three test accounts.
Results are printed and saved to rules_test_results.txt.
"""
import base64
import datetime
import getpass
import json
import os
import sys

import firebase_admin
import requests
from firebase_admin import auth, credentials, firestore

CRED_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")
ACCOUNTS = {
    "borrower": "borrower@test.com",
    "broker": "broker@test.com",
    "underwriter": "underwriter@test.com",
}
OTHER_BORROWER_UID = "someone-else-uid"
OTHER_BROKER_UID = "someone-else-broker"

with open(CRED_PATH) as f:
    PROJECT_ID = json.load(f)["project_id"]
BASE = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"

results = []


# ---------------------------------------------------------------- helpers
def sign_in(api_key, email, password):
    r = requests.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}",
        json={"email": email, "password": password, "returnSecureToken": True},
        timeout=20,
    )
    if r.status_code != 200:
        msg = r.json().get("error", {}).get("message", r.text)
        sys.exit(f"Sign-in failed for {email}: {msg}")
    data = r.json()
    return data["idToken"], data["localId"]


def token_role(id_token):
    payload = id_token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload)).get("role")


def to_fields(d):
    out = {}
    for k, v in d.items():
        if isinstance(v, bool):
            out[k] = {"booleanValue": v}
        elif isinstance(v, int):
            out[k] = {"integerValue": str(v)}
        elif isinstance(v, float):
            out[k] = {"doubleValue": v}
        else:
            out[k] = {"stringValue": str(v)}
    return {"fields": out}


def call(method, suffix, token=None, **kwargs):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.request(method, f"{BASE}{suffix}", headers=headers, timeout=20, **kwargs).status_code


def check(tc, desc, expect_allowed, status, write=False):
    allowed_codes = (200,) if write else (200, 404)
    if status in allowed_codes:
        got = "ALLOW"
    elif status in (401, 403):
        got = "DENY"
    else:
        got = "ERROR"
    expected = "ALLOW" if expect_allowed else "DENY"
    outcome = "PASS" if got == expected else "FAIL"
    line = f"{outcome}  {tc:<7} {desc:<66} expected {expected:<5} got {got:<5} (HTTP {status})"
    print(line)
    results.append((outcome, line))


def get_doc(path, token):
    return call("GET", f"/{path}", token)


def create_doc(collection, doc_id, data, token):
    return call("POST", f"/{collection}?documentId={doc_id}", token, json=to_fields(data))


def update_doc(path, data, token):
    mask = "&".join(f"updateMask.fieldPaths={k}" for k in data)
    return call("PATCH", f"/{path}?{mask}", token, json=to_fields(data))


def run_query(token, uid=None):
    query = {"from": [{"collectionId": "applications"}]}
    if uid:
        query["where"] = {
            "fieldFilter": {"field": {"fieldPath": "borrowerId"}, "op": "EQUAL", "value": {"stringValue": uid}}
        }
    return call("POST", ":runQuery", token, json={"structuredQuery": query})


# ---------------------------------------------------------------- main
def main():
    api_key = os.environ.get("FIREBASE_API_KEY") or input("Firebase web apiKey: ").strip()
    password = os.environ.get("TEST_PASSWORD") or getpass.getpass("Password for the three test accounts: ")

    firebase_admin.initialize_app(credentials.Certificate(CRED_PATH))
    db = firestore.client()

    tokens, uids = {}, {}
    for role, email in ACCOUNTS.items():
        tokens[role], uids[role] = sign_in(api_key, email, password)
        seen = token_role(tokens[role])
        print(f"Signed in {email}: role claim in token = {seen}")
        if seen != role:
            sys.exit(f"\n{email} should have role '{role}' but the token has '{seen}'. "
                     f"Run assign_roles.py and try again (the fresh sign-in should pick it up).")
    print()

    b, br, u = tokens["borrower"], tokens["broker"], tokens["underwriter"]
    b_uid, br_uid = uids["borrower"], uids["broker"]

    user_doc_ref = db.collection("users").document(b_uid)
    user_doc_existed = user_doc_ref.get().exists

    created_ids = [
        "rules_test_own", "rules_test_other", "rules_test_draft",
        "rules_test_created", "rules_test_funded", "rules_test_tx",
        "rules_test_broker", "rules_test_anon",
    ]

    try:
        # Seed test data (Admin SDK bypasses the rules)
        apps = db.collection("applications")
        apps.document("rules_test_own").set(
            {"borrowerId": b_uid, "brokerId": br_uid, "status": "Applied", "loanAmount": 300000})
        apps.document("rules_test_other").set(
            {"borrowerId": OTHER_BORROWER_UID, "brokerId": OTHER_BROKER_UID, "status": "Applied", "loanAmount": 250000})
        apps.document("rules_test_draft").set(
            {"borrowerId": b_uid, "status": "Draft", "loanAmount": 200000})

        # TC4.1 / 4.2 borrower reads
        check("TC4.1", "Borrower reads their own application", True, get_doc("applications/rules_test_own", b))
        check("TC4.2", "Borrower reads another borrower's application", False, get_doc("applications/rules_test_other", b))
        check("TC4.2b", "Borrower runs an unfiltered query on all applications", False, run_query(b))
        check("TC4.2c", "Borrower queries applications where borrowerId == own uid", True, run_query(b, b_uid))

        # TC4.3 broker reads
        check("TC4.3a", "Broker reads an application assigned to them", True, get_doc("applications/rules_test_own", br))
        check("TC4.3b", "Broker reads an application not assigned to them", False, get_doc("applications/rules_test_other", br))

        # TC4.4 underwriter reads
        check("TC4.4a", "Underwriter reads any application (assigned one)", True, get_doc("applications/rules_test_own", u))
        check("TC4.4b", "Underwriter reads any application (someone else's)", True, get_doc("applications/rules_test_other", u))

        # TC4.5 write restrictions
        check("TC4.5a", "Borrower creates an application with status 'Funded'", False,
              create_doc("applications", "rules_test_funded",
                         {"borrowerId": b_uid, "status": "Funded", "loanAmount": 1}, b), write=True)
        check("TC4.5b", "Borrower creates an application containing txHash", False,
              create_doc("applications", "rules_test_tx",
                         {"borrowerId": b_uid, "status": "Draft", "txHash": "0xabc"}, b), write=True)
        check("TC4.5c", "Borrower creates a valid Draft application for themselves", True,
              create_doc("applications", "rules_test_created",
                         {"borrowerId": b_uid, "status": "Draft", "loanAmount": 100000}, b), write=True)
        check("TC4.5d", "Borrower updates loanAmount on their own Draft", True,
              update_doc("applications/rules_test_draft", {"loanAmount": 210000}, b), write=True)
        check("TC4.5e", "Borrower sets txHash on their own Draft", False,
              update_doc("applications/rules_test_draft", {"txHash": "0xabc"}, b), write=True)
        check("TC4.5f", "Borrower edits their own application once it is 'Applied'", False,
              update_doc("applications/rules_test_own", {"loanAmount": 1}, b), write=True)
        check("TC4.5g", "Broker creates an application", False,
              create_doc("applications", "rules_test_broker",
                         {"borrowerId": br_uid, "status": "Draft", "loanAmount": 1}, br), write=True)

        # TC4.6 unauthenticated
        check("TC4.6a", "Unauthenticated user reads an application", False, get_doc("applications/rules_test_own", None))
        check("TC4.6b", "Unauthenticated user creates an application", False,
              create_doc("applications", "rules_test_anon", {"borrowerId": "x", "status": "Draft"}, None), write=True)

        # TC4.7 users collection
        check("TC4.7a", "Borrower writes own profile with a 'role' field", False,
              update_doc(f"users/{b_uid}", {"name": "Test Borrower", "role": "underwriter"}, b), write=True)
        check("TC4.7b", "Borrower writes own profile without a 'role' field", True,
              update_doc(f"users/{b_uid}", {"name": "Test Borrower"}, b), write=True)
        check("TC4.7c", "Borrower reads another user's profile", False, get_doc(f"users/{uids['underwriter']}", b))

        # TC4.8 audit records
        check("TC4.8a", "Borrower reads auditRecords", False, get_doc("auditRecords/anything", b))
        check("TC4.8b", "Underwriter reads auditRecords", True, get_doc("auditRecords/anything", u))
    finally:
        # Remove everything the test created
        for doc_id in created_ids:
            db.collection("applications").document(doc_id).delete()
        if not user_doc_existed:
            user_doc_ref.delete()
        print("\nTest data removed.")

    passed = sum(1 for o, _ in results if o == "PASS")
    total = len(results)
    summary = f"\n{passed}/{total} checks passed"
    print(summary)

    with open("rules_test_results.txt", "w", encoding="utf-8") as f:
        f.write("Firestore security rules test\n")
        f.write(f"Project: {PROJECT_ID}\n")
        f.write(f"Run: {datetime.datetime.now():%Y-%m-%d %H:%M}\n")
        f.write("Accounts: " + ", ".join(f"{e} ({r})" for r, e in ACCOUNTS.items()) + "\n\n")
        for _, line in results:
            f.write(line + "\n")
        f.write(summary + "\n")
    print("Saved to rules_test_results.txt")


if __name__ == "__main__":
    main()

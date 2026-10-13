"""
Assign a role (custom claim) to Firebase users.

Usage:
    python assign_roles.py                          # sets the three default test accounts
    python assign_roles.py someone@example.com broker   # sets one user's role

The user must sign out and back in (or refresh their ID token) before
the new role appears in their token.
"""
import os
import sys

import firebase_admin
from firebase_admin import auth, credentials

CRED_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")
VALID_ROLES = {"borrower", "broker", "underwriter"}

DEFAULT_TEST_USERS = {
    "borrower@test.com": "borrower",
    "broker@test.com": "broker",
    "underwriter@test.com": "underwriter",
}


def set_role(email, role):
    if role not in VALID_ROLES:
        print(f"[skip] {email}: '{role}' is not a valid role {sorted(VALID_ROLES)}")
        return
    try:
        user = auth.get_user_by_email(email)
    except auth.UserNotFoundError:
        print(f"[skip] {email}: no such user. Create it in Authentication first.")
        return
    auth.set_custom_user_claims(user.uid, {"role": role})
    print(f"[ok]   {email} (uid {user.uid}) -> role '{role}'")


def main():
    firebase_admin.initialize_app(credentials.Certificate(CRED_PATH))

    if len(sys.argv) == 3:
        set_role(sys.argv[1], sys.argv[2])
    elif len(sys.argv) == 1:
        for email, role in DEFAULT_TEST_USERS.items():
            set_role(email, role)
    else:
        print("Usage: python assign_roles.py [email role]")
        sys.exit(1)

    print("\nUsers must sign out and back in for the new role to take effect.")


if __name__ == "__main__":
    main()

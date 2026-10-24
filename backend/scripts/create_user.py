"""Create a real board-member account (passwords are typed, never stored in code).

    python -m backend.scripts.create_user --email lily@example.org --first Lily --last Milone --role chair
"""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from backend.app.core.config import get_settings
from backend.app.core.permissions import Role
from backend.app.core.security import MIN_PASSWORD_LENGTH, hash_password
from backend.app.db.database import Database
from backend.app.db.models import BoardMembership, Organization, User

TITLES = {"chair": "Board Chair", "treasurer": "Treasurer", "member": "Board Member"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--first", required=True)
    parser.add_argument("--last", default="")
    parser.add_argument("--role", choices=[r.value for r in Role], default="member")
    args = parser.parse_args()

    password = getpass.getpass(f"Password for {args.email} (min {MIN_PASSWORD_LENGTH} characters): ")
    if len(password) < MIN_PASSWORD_LENGTH or password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords must match and be at least 10 characters.")

    db = Database(get_settings().database_path)
    db.initialize()
    with db.transaction() as session:
        email = args.email.strip().lower()
        if session.scalar(select(User).where(User.email == email)):
            sys.exit(f"{email} already exists.")
        org = session.scalar(select(Organization).order_by(Organization.id).limit(1))
        user = User(email=email, first_name=args.first, last_name=args.last, password_hash=hash_password(password))
        session.add(user)
        session.flush()
        session.add(BoardMembership(user_id=user.id, organization_id=org.id, role=args.role, title=TITLES[args.role]))
    print(f"Created {email} ({args.role}) in {org.name}.")


if __name__ == "__main__":
    main()

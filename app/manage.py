import argparse
from getpass import getpass
from sqlalchemy import select
from .db import Audit, Base, Session, User, engine
from .schemas import Credentials
from .security import hasher


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=["admin", "reviewer", "handler"])
    parser.add_argument("email")
    args = parser.parse_args()
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine)
    with Session.begin() as db:
        email = args.email.lower()
        user = db.scalar(select(User).where(User.email == email))
        if not user:
            account = Credentials(email=email, password=getpass("New password (10+ characters): "))
            user = User(email=email, password_hash=hasher.hash(account.password))
            db.add(user)
            db.flush()
        user.role = args.role
        db.add(Audit(action="operator.role", entity_id=user.id, details={"role": args.role}))
    print("Account role saved.")


if __name__ == "__main__":
    main()

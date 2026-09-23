"""One-off: creates the first super_admin account — there's no UI for this
(registering through /auth/register always creates a plain 'user', by
design, so nobody can self-promote), so bootstrapping the very first one
has to happen directly against the DB.

Run from meeting-bot/: python create_super_admin.py
"""

import getpass

from dotenv import load_dotenv

load_dotenv()

from pipeline import auth_store  # noqa: E402


def main():
    email = input("Email: ").strip()
    name = input("Nama: ").strip()
    password = getpass.getpass("Password (min 8 karakter): ")
    if len(password) < 8:
        print("Password minimal 8 karakter.")
        return

    user = auth_store.create_user(email, password, name, role="super_admin")
    print(f"Super admin dibuat: {user['email']} ({user['id']})")


if __name__ == "__main__":
    main()

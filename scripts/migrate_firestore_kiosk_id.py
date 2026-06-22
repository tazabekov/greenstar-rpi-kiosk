#!/usr/bin/env python3
"""
One-shot migration: copy /kiosks/kiosk-001 → /kiosks/01-test-kiosk in Firestore.

Copies:
  - the top-level kiosk document
  - all documents in /transactions subcollection
  - all documents in /metrics subcollection

Requires FIREBASE_SERVICE_ACCOUNT_JSON in .env (same as the kiosk app).
Run once; the old document is NOT deleted automatically — delete it manually
after verifying the new one looks correct in the Firebase console.

Usage:
    cd /home/ali/code/greenstar-rpi-kiosk
    python3 scripts/migrate_firestore_kiosk_id.py
"""

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ImportError:
    sys.exit("firebase-admin not installed. Run: pip3 install firebase-admin")

OLD_ID = "kiosk-001"
NEW_ID = "01-test-kiosk"

sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
if not sa_json:
    sys.exit("FIREBASE_SERVICE_ACCOUNT_JSON not set in .env")

cred = credentials.Certificate(json.loads(sa_json))
firebase_admin.initialize_app(cred)
db = firestore.client()


def copy_subcollection(src_ref, dst_ref, name: str):
    docs = list(src_ref.collection(name).stream())
    if not docs:
        print(f"  {name}/: (empty)")
        return
    batch = db.batch()
    for doc in docs:
        batch.set(dst_ref.collection(name).document(doc.id), doc.to_dict())
    batch.commit()
    print(f"  {name}/: copied {len(docs)} documents")


src = db.collection("kiosks").document(OLD_ID)
dst = db.collection("kiosks").document(NEW_ID)

src_snap = src.get()
if not src_snap.exists:
    sys.exit(f"Source document /kiosks/{OLD_ID} does not exist — nothing to migrate")

data = src_snap.to_dict()
data["kiosk_id"] = NEW_ID
dst.set(data)
print(f"Copied /kiosks/{OLD_ID} → /kiosks/{NEW_ID}")

copy_subcollection(src, dst, "transactions")
copy_subcollection(src, dst, "metrics")

print()
print("Done. Verify /kiosks/01-test-kiosk in the Firebase console, then")
print(f"manually delete /kiosks/{OLD_ID} if everything looks good.")

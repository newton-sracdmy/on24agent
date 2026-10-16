"""Re-encrypt stored credentials under the current ENCRYPTION_KEY.

Rotation steps:
  1. Move the old key into ENCRYPTION_KEY_PREVIOUS (JSON list) and set a new ENCRYPTION_KEY.
  2. Run: python -m scripts.rotate_encryption_key
  3. Remove the old key from ENCRYPTION_KEY_PREVIOUS.
"""

import asyncio

from sqlalchemy import text

from app.database import admin_engine
from app.security import get_cipher

ENCRYPTED_COLUMNS = [
    ("channel_accounts", "encrypted_credentials"),
    ("integrations", "encrypted_credentials"),
]


async def rotate() -> None:
    cipher = get_cipher()
    async with admin_engine.begin() as conn:
        for table, column in ENCRYPTED_COLUMNS:
            rows = (
                await conn.execute(text(f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL AND {column} <> ''"))
            ).all()
            for row_id, token in rows:
                rotated = cipher.rotate(token.encode("utf-8")).decode("utf-8")
                await conn.execute(
                    text(f"UPDATE {table} SET {column} = :value WHERE id = :id"),
                    {"value": rotated, "id": row_id},
                )
            print(f"{table}.{column}: re-encrypted {len(rows)} row(s)")


if __name__ == "__main__":
    asyncio.run(rotate())

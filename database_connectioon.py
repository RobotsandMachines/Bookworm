"""
Supabase + PostgreSQL Book Store Database Client
================================================

This module is a *single-file* Python “application” you can drop into a project to:
- Connect to Supabase using the **supabase** (supabase-py) package for row-level CRUD.
- Connect to the underlying **PostgreSQL** database using **psycopg** for schema/field-level operations.
- Provide functions to insert, delete, search, update, and list records.
- Provide a few “field” utilities (add/rename columns).
- Include a **DROP COLUMN** function that is **entirely commented out** so it cannot run by accident.

Table fields (with types):
- id (int8)
- title (text)
- ISBN_10 (numeric)
- ISBN_13 (numeric)
- year (date)
- edition (numeric)
- cover_type (bool)
- genres (jsonb)
- length (numeric)
- amount_in_store (numeric)
- price (numeric)
- discounts (numeric)
- publisher (text)
- author (text)
- language (text)

Prereqs:
    pip install supabase psycopg python-dotenv

Environment variables (recommended in a .env file):
    SUPABASE_URL="https://xxxxx.supabase.co"
    SUPABASE_SERVICE_ROLE_KEY="..."   # or SUPABASE_ANON_KEY (service role is better for server-side apps)
    SUPABASE_DB_DSN="postgresql://user:password@host:5432/postgres"

Notes:
- Supabase CRUD uses the Supabase REST interface (PostgREST).
- Schema changes (ALTER TABLE) are done via direct Postgres connection.
- Use service-role key only on trusted backends (never ship it to browsers/apps).

"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Union
from dotenv import load_dotenv

import os

from supabase import create_client, Client as SupabaseClient
import psycopg

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL not found. Is your .env in the project root?")
if not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_KEY not found. Is it set in .env?")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------------
# Configuration
# -----------------------------

DEFAULT_TABLE_NAME = "books"


def _get_env(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


def make_supabase_client() -> SupabaseClient:
    url = _get_env("SUPABASE_URL")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
    )

    if not key:
        raise RuntimeError(
            "Missing SUPABASE_SERVICE_ROLE_KEY, SUPABASE_KEY, or SUPABASE_ANON_KEY"
        )

    return create_client(url, key)



def make_pg_connection():
    """
    Creates a psycopg connection for schema/field operations.
    Requires:
      - SUPABASE_DB_DSN  (preferred), or DATABASE_URL
    """
    dsn = os.getenv("SUPABASE_DB_DSN") or os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Missing SUPABASE_DB_DSN (or DATABASE_URL)")
    return psycopg.connect(dsn)


# -----------------------------
# Data Model + Validation Helpers
# -----------------------------

NumericLike = Union[int, float, str, Decimal]
JsonLike = Union[Dict[str, Any], List[Any]]


def _to_decimal(value: Optional[NumericLike], field_name: str) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        # Convert via str to preserve large numeric-like inputs (e.g., ISBNs)
        return Decimal(str(value))
    except Exception as e:
        raise ValueError(f"Field '{field_name}' must be numeric-like. Got: {value!r}") from e


def _to_date(value: Optional[Union[str, date, datetime]], field_name: str) -> Optional[str]:
    """
    Return YYYY-MM-DD string suitable for Postgres date columns (and PostgREST).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        # Expect ISO format "YYYY-MM-DD"
        try:
            return date.fromisoformat(value).isoformat()
        except Exception as e:
            raise ValueError(f"Field '{field_name}' must be ISO date 'YYYY-MM-DD'. Got: {value!r}") from e
    raise ValueError(f"Field '{field_name}' must be date/datetime/ISO str. Got: {type(value).__name__}")


def _ensure_bool(value: Optional[bool], field_name: str) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise ValueError(f"Field '{field_name}' must be boolean. Got: {value!r}")


def _ensure_text(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise ValueError(f"Field '{field_name}' must be text (str). Got: {value!r}")


def _ensure_jsonb(value: Optional[JsonLike], field_name: str) -> Optional[JsonLike]:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    raise ValueError(f"Field '{field_name}' must be dict or list for jsonb. Got: {value!r}")


@dataclass
class BookRecord:
    """
    Represents a row in the books table.
    You can omit id on insert (Postgres identity/serial recommended).
    """
    id: Optional[int] = None  # int8
    title: Optional[str] = None  # text
    ISBN_10: Optional[NumericLike] = None  # numeric
    ISBN_13: Optional[NumericLike] = None  # numeric
    year: Optional[Union[str, date, datetime]] = None  # date
    edition: Optional[NumericLike] = None  # numeric
    cover_type: Optional[bool] = None  # bool
    genres: Optional[JsonLike] = None  # jsonb
    length: Optional[NumericLike] = None  # numeric
    amount_in_store: Optional[NumericLike] = None  # numeric
    price: Optional[NumericLike] = None  # numeric
    discounts: Optional[NumericLike] = None  # numeric
    publisher: Optional[str] = None  # text
    author: Optional[str] = None  # text
    language: Optional[str] = None  # text

    def to_db_payload(self, include_id: bool = False) -> Dict[str, Any]:
        """
        Converts this record into a payload compatible with Supabase/PostgREST.
        - Converts numeric fields to Decimal (then to str to avoid float rounding).
        - Converts year to ISO date string.
        """
        payload: Dict[str, Any] = {}

        if include_id and self.id is not None:
            if not isinstance(self.id, int):
                raise ValueError(f"Field 'id' must be int. Got: {self.id!r}")
            payload["id"] = self.id

        if self.title is not None:
            payload["title"] = _ensure_text(self.title, "title")

        if self.ISBN_10 is not None:
            payload["ISBN_10"] = str(_to_decimal(self.ISBN_10, "ISBN_10"))

        if self.ISBN_13 is not None:
            payload["ISBN_13"] = str(_to_decimal(self.ISBN_13, "ISBN_13"))

        if self.year is not None:
            payload["year"] = _to_date(self.year, "year")

        if self.edition is not None:
            payload["edition"] = str(_to_decimal(self.edition, "edition"))

        if self.cover_type is not None:
            payload["cover_type"] = _ensure_bool(self.cover_type, "cover_type")

        if self.genres is not None:
            payload["genres"] = _ensure_jsonb(self.genres, "genres")

        if self.length is not None:
            payload["length"] = str(_to_decimal(self.length, "length"))

        if self.amount_in_store is not None:
            payload["amount_in_store"] = str(_to_decimal(self.amount_in_store, "amount_in_store"))

        if self.price is not None:
            payload["price"] = str(_to_decimal(self.price, "price"))

        if self.discounts is not None:
            payload["discounts"] = str(_to_decimal(self.discounts, "discounts"))

        if self.publisher is not None:
            payload["publisher"] = _ensure_text(self.publisher, "publisher")

        if self.author is not None:
            payload["author"] = _ensure_text(self.author, "author")

        if self.language is not None:
            payload["language"] = _ensure_text(self.language, "language")

        return payload


# -----------------------------
# Supabase CRUD (Records)
# -----------------------------

class BookStoreDB:
    """
    Main interface:
      - Supabase client for row-level operations
      - psycopg connection for schema changes (field-level ops)
    """

    def __init__(self, table_name: str = DEFAULT_TABLE_NAME):
        self.table_name = table_name
        self.sb: SupabaseClient = make_supabase_client()

    # ---------- Insert ----------
    def insert_book(self, book: BookRecord) -> Dict[str, Any]:
        """
        Insert a new book record. (id usually omitted)
        Returns the inserted row (as dict).
        """
        payload = book.to_db_payload(include_id=False)
        resp = self.sb.table(self.table_name).insert(payload).execute()
        self._raise_on_error(resp)
        return resp.data[0] if resp.data else {}

    def insert_many(self, books: Sequence[BookRecord]) -> List[Dict[str, Any]]:
        """
        Bulk insert.
        """
        payloads = [b.to_db_payload(include_id=False) for b in books]
        resp = self.sb.table(self.table_name).insert(payloads).execute()
        self._raise_on_error(resp)
        return resp.data or []

    # ---------- Delete ----------
    def delete_book_by_id(self, book_id: int) -> int:
        """
        Delete a record by id.
        Returns number of rows deleted (best-effort; depends on returning settings).
        """
        if not isinstance(book_id, int):
            raise ValueError("book_id must be int")
        resp = self.sb.table(self.table_name).delete().eq("id", book_id).execute()
        self._raise_on_error(resp)
        # resp.data often includes deleted rows if returning is enabled; otherwise may be empty
        return len(resp.data or [])

    def delete_books_by_author(self, author: str) -> int:
        """
        Delete records matching a given author.
        """
        author = _ensure_text(author, "author") or ""
        resp = self.sb.table(self.table_name).delete().eq("author", author).execute()
        self._raise_on_error(resp)
        return len(resp.data or [])

    # ---------- Update ----------
    def update_book_by_id(self, book_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update a record by id with a partial updates dict.
        Tip: if you want validation, build a BookRecord and call .to_db_payload().
        """
        if not isinstance(book_id, int):
            raise ValueError("book_id must be int")
        if not isinstance(updates, dict) or not updates:
            raise ValueError("updates must be a non-empty dict")

        resp = self.sb.table(self.table_name).update(updates).eq("id", book_id).execute()
        self._raise_on_error(resp)
        return resp.data[0] if resp.data else {}

    # ---------- Search / Query ----------
    def get_book_by_id(self, book_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch a single record by id.
        """
        if not isinstance(book_id, int):
            raise ValueError("book_id must be int")
        resp = self.sb.table(self.table_name).select("*").eq("id", book_id).limit(1).execute()
        self._raise_on_error(resp)
        return resp.data[0] if resp.data else None

    def search_books(
        self,
        title_contains: Optional[str] = None,
        author_contains: Optional[str] = None,
        publisher_contains: Optional[str] = None,
        isbn10: Optional[NumericLike] = None,
        isbn13: Optional[NumericLike] = None,
        language: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Flexible search.
        Uses PostgREST filters:
          - ilike for contains (case-insensitive)
          - eq for exact ISBN / language
        """
        q = self.sb.table(self.table_name).select("*")

        if title_contains:
            q = q.ilike("title", f"%{title_contains}%")
        if author_contains:
            q = q.ilike("author", f"%{author_contains}%")
        if publisher_contains:
            q = q.ilike("publisher", f"%{publisher_contains}%")
        if isbn10 is not None:
            q = q.eq("ISBN_10", str(_to_decimal(isbn10, "ISBN_10")))
        if isbn13 is not None:
            q = q.eq("ISBN_13", str(_to_decimal(isbn13, "ISBN_13")))
        if language:
            q = q.eq("language", language)

        resp = q.limit(limit).execute()
        self._raise_on_error(resp)
        return resp.data or []

    def list_books(self, limit: int = 100, order_by: str = "id", ascending: bool = True) -> List[Dict[str, Any]]:
        """
        List books with ordering.
        """
        resp = (
            self.sb.table(self.table_name)
            .select("*")
            .order(order_by, desc=not ascending)
            .limit(limit)
            .execute()
        )
        self._raise_on_error(resp)
        return resp.data or []

    # ---------- Helpers ----------
    @staticmethod
    def _raise_on_error(resp: Any) -> None:
        """
        supabase-py returns a response object with .data and .error
        """
        err = getattr(resp, "error", None)
        if err:
            raise RuntimeError(f"Supabase error: {err}")


# -----------------------------
# PostgreSQL Schema / Field Operations
# -----------------------------

def add_field(table_name: str, field_name: str, postgres_type: str) -> None:
    """
    Add a column to the table using direct Postgres.
    Example:
        add_field("books", "subtitle", "text")
        add_field("books", "tags", "jsonb")
    """
    if not table_name or not field_name or not postgres_type:
        raise ValueError("table_name, field_name, and postgres_type are required")

    sql = f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{field_name}" {postgres_type};'
    with make_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def rename_field(table_name: str, old_field_name: str, new_field_name: str) -> None:
    """
    Rename a column using direct Postgres.
    """
    if not table_name or not old_field_name or not new_field_name:
        raise ValueError("table_name, old_field_name, and new_field_name are required")

    sql = f'ALTER TABLE "{table_name}" RENAME COLUMN "{old_field_name}" TO "{new_field_name}";'
    with make_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


# --------------------------------------------------------------------------------
# DELETE FIELD (DROP COLUMN) — ENTIRELY COMMENTED OUT ON PURPOSE
# You asked for the code but to make sure it cannot execute even by accident.
# --------------------------------------------------------------------------------

# def delete_field(table_name: str, field_name: str) -> None:
#     """
#     DANGER: Drops a column from the table (irreversible without backups).
#     Intentionally commented out to prevent accidental execution.
#
#     Usage would have been:
#         delete_field("books", "some_column")
#     """
#     if not table_name or not field_name:
#         raise ValueError("table_name and field_name are required")
#
#     sql = f'ALTER TABLE "{table_name}" DROP COLUMN IF EXISTS "{field_name}";'
#     with make_pg_connection() as conn:
#         with conn.cursor() as cur:
#             cur.execute(sql)
#         conn.commit()


# -----------------------------
# Example Usage (safe to keep; does nothing unless you run it)
# -----------------------------

def _example():
    db = BookStoreDB(table_name="books")

    # Insert one
    inserted = db.insert_book(
        BookRecord(
            title="The Hobbit",
            ISBN_10="0618968636",
            ISBN_13="9780618968633",
            year="1937-09-21",
            edition=1,
            cover_type=True,
            genres=["Fantasy", "Adventure"],
            length=310,
            amount_in_store=12,
            price="12.99",
            discounts="0.00",
            publisher="George Allen & Unwin",
            author="J. R. R. Tolkien",
            language="English",
        )
    )
    print("Inserted:", inserted)

    # Search
    results = db.search_books(title_contains="Hobbit", limit=10)
    print("Search results:", results)

    # Update by id
    if inserted.get("id") is not None:
        updated = db.update_book_by_id(int(inserted["id"]), {"amount_in_store": "11"})
        print("Updated:", updated)

    # Delete by id
    if inserted.get("id") is not None:
        deleted_count = db.delete_book_by_id(int(inserted["id"]))
        print("Deleted rows:", deleted_count)


if __name__ == "__main__":
    # Uncomment to test manually:
    # _example()
    pass

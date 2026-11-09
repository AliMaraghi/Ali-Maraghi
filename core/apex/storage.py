import os

SCHEMA = """
CREATE TABLE IF NOT EXISTS public_observations (
 id BIGSERIAL PRIMARY KEY,
 source TEXT NOT NULL,
 title TEXT NOT NULL,
 url TEXT NOT NULL UNIQUE,
 observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

def connection():
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)

def ensure_schema():
    with connection() as db:
        db.execute(SCHEMA)

def list_items(limit=30):
    with connection() as db:
        return db.execute("SELECT source,title,url,observed_at FROM public_observations ORDER BY observed_at DESC LIMIT %s",(limit,)).fetchall()

def upsert(source, title, url):
    with connection() as db:
        db.execute("INSERT INTO public_observations (source,title,url) VALUES (%s,%s,%s) ON CONFLICT (url) DO NOTHING", (source,title,url))

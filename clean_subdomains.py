import psycopg2
import tldextract
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://leadscope:leadscope_dev@localhost:5432/leadscope")

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True

with conn.cursor() as cur:
    cur.execute("SELECT id, domain FROM candidates")
    rows = cur.fetchall()

ids_to_delete = []
for id, domain in rows:
    ext = tldextract.extract(domain)
    if ext.subdomain and ext.subdomain != 'www':
        ids_to_delete.append(id)

if ids_to_delete:
    print(f"Deleting {len(ids_to_delete)} subdomains...")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM candidates WHERE id = ANY(%s)", (ids_to_delete,))
    print("Done!")
else:
    print("No subdomains found.")

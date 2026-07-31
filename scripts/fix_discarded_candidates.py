import os
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://leadscope:leadscope_dev@postgres:5432/leadscope")

def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        # Reset candidates in 'discarded' status back to 'new' if they have never been evaluated/enriched
        query = """
        UPDATE candidates 
        SET status = 'new' 
        WHERE status = 'discarded' 
          AND evaluated_at IS NULL 
          AND enrichment_attempt_count = 0
        RETURNING domain;
        """
        cur.execute(query)
        rows = cur.fetchall()
        print(f"Reopened {len(rows)} discarded candidates back to 'new':")
        for row in rows:
            print(f" - {row[0]}")

if __name__ == "__main__":
    main()

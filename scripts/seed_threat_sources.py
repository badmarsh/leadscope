import os
import psycopg2
from psycopg2.extras import DictCursor
import urllib.parse

# Database connection parameters
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://leadscope:leadscope_dev@localhost:5432/leadscope")
parsed_url = urllib.parse.urlparse(DATABASE_URL)
# Ensure we use localhost for the external script, since docker-compose exposes port 5432
db_params = {
    "dbname": parsed_url.path[1:],
    "user": parsed_url.username,
    "password": parsed_url.password,
    "host": "localhost",
    "port": parsed_url.port
}

SEED_SOURCES = [
    {
        "name": "cside.com Blog",
        "url": "https://cside.com/blog",
        "type": "scraping"
    },
    {
        "name": "WPScan Blog",
        "url": "https://wpscan.com/blog/feed/",
        "type": "rss"
    },
    {
        "name": "Patchstack Blog",
        "url": "https://patchstack.com/database/vulnerabilities",
        "type": "scraping"
    },
    {
        "name": "BleepingComputer",
        "url": "https://www.bleepingcomputer.com/feed/",
        "type": "rss"
    },
    {
        "name": "The Hacker News",
        "url": "https://feeds.feedburner.com/TheHackersNews",
        "type": "rss"
    }
]

def seed_threat_sources():
    try:
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor()
        
        print("Seeding threat intel sources...")
        count = 0
        for source in SEED_SOURCES:
            cursor.execute("""
                INSERT INTO threat_intel_sources (name, url, type)
                VALUES (%s, %s, %s)
            """, (source["name"], source["url"], source["type"]))
            if cursor.rowcount > 0:
                print(f"Added source: {source['name']}")
                count += 1
                
        conn.commit()
        print(f"Done! Inserted {count} new sources.")
        
    except Exception as e:
        print(f"Error seeding database: {e}")
    finally:
        if 'conn' in locals():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    seed_threat_sources()

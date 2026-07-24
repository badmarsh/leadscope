import tldextract
import psycopg2

def clean_subdomains():
    conn = psycopg2.connect("postgresql://leadscope:leadscope_dev@postgres:5432/leadscope")
    cur = conn.cursor()
    
    cur.execute("SELECT id, domain FROM candidates")
    candidates = cur.fetchall()
    
    subdomain_ids = []
    for cid, domain in candidates:
        ext = tldextract.extract(domain)
        if ext.subdomain and ext.subdomain != 'www':
            subdomain_ids.append(cid)
            
    if subdomain_ids:
        print(f"Found {len(subdomain_ids)} subdomains to delete.")
        # chunk the deletions to avoid massive queries
        for idx in range(0, len(subdomain_ids), 100):
            chunk = tuple(subdomain_ids[idx:idx+100])
            if len(chunk) == 1:
                chunk_str = f"({chunk[0]})"
            else:
                chunk_str = str(chunk)
            
            cur.execute(f"DELETE FROM leads WHERE candidate_id IN {chunk_str}")
            cur.execute(f"DELETE FROM feedback WHERE candidate_id IN {chunk_str}")
            cur.execute(f"DELETE FROM evaluations WHERE candidate_id IN {chunk_str}")
            cur.execute(f"DELETE FROM candidates WHERE id IN {chunk_str}")
            
        conn.commit()
        print("Cleanup complete.")
    else:
        print("No subdomains found.")
        
    cur.close()
    conn.close()

if __name__ == '__main__':
    clean_subdomains()

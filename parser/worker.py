import time
import os
import json
import traceback
import shutil
import psycopg2
from psycopg2.extras import RealDictCursor
from parse_document import parse_pdf 

DB_URL = os.environ.get("DATABASE_URL")

# 1. Retention Policy: How old must a job be to get deleted?
# Default: 24 Hours
RETENTION_HOURS = int(os.environ.get("RETENTION_HOURS", 24))

# 2. Janitor Frequency: How often does the janitor wake up to check?
# Default: 300 seconds (5 minutes). 
CLEANUP_INTERVAL_SECONDS = int(os.environ.get("CLEANUP_INTERVAL_SECONDS", 300))


def get_db_connection():
    return psycopg2.connect(DB_URL)

def cleanup_old_jobs(conn):
    """
    The Janitor: Permanently deletes files for jobs older than RETENTION_HOURS.
    """
    try:
        with conn.cursor() as cur:
            # Postgres math: NOW() - INTERVAL '24 hours'
            # We use an f-string here to inject the integer safely into the interval syntax
            query = f"""
                SELECT id, input_file, output_dir FROM jobs 
                WHERE status = 'COMPLETED' 
                AND completed_at < NOW() - INTERVAL '{RETENTION_HOURS} HOURS'
            """
            cur.execute(query)
            old_jobs = cur.fetchall()
            
            if not old_jobs:
                return

            print(f"[Janitor] Found {len(old_jobs)} expired jobs (older than {RETENTION_HOURS}h)...")

            for job in old_jobs:
                job_id, input_file, output_dir = job
                
                # 1. Delete Input PDF
                if input_file:
                    input_path = os.path.join("/app/uploads", input_file)
                    if os.path.exists(input_path):
                        os.remove(input_path)

                # 2. Delete Output Folder
                if output_dir:
                    output_path = os.path.join("/app/uploads", output_dir)
                    if os.path.exists(output_path):
                        shutil.rmtree(output_path)

                # 3. Update Status
                cur.execute("UPDATE jobs SET status = 'PURGED' WHERE id = %s", (job_id,))
            
            conn.commit()
            print(f"[Janitor] Successfully purged {len(old_jobs)} jobs.")
                
    except Exception as e:
        print(f"⚠️ Janitor Error: {e}")
        conn.rollback()

def process_job(conn, job):
    job_id = job['id']
    input_path = os.path.join("/app/uploads", job['input_file'])
    output_dir = os.path.join("/app/uploads", job['output_dir'])
    
    print(f"[Job {job_id}] Starting processing...")
    
    try:
        # 1. Create Output Dir
        os.makedirs(output_dir, exist_ok=True)
        
        # 2. Parse
        parse_pdf(input_path, output_dir)
        
        # 3. Read Page Count
        meta_path = os.path.join(output_dir, "document.json")
        page_count = 0
        if os.path.exists(meta_path):
            with open(meta_path, 'r') as f:
                data = json.load(f)
                page_count = data.get("pages", 0)

        # 4. Update DB
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE jobs 
                SET status = 'COMPLETED', 
                    completed_at = NOW(),
                    page_count = %s
                WHERE id = %s
            """, (page_count, job_id))
        conn.commit()
        print(f"[Job {job_id}] Completed. Pages: {page_count}")

    except Exception as e:
        print(f"[Job {job_id}] Failed: {e}")
        traceback.print_exc()
        conn.rollback()
        
        with conn.cursor() as cur:
            cur.execute("UPDATE jobs SET status = 'FAILED' WHERE id = %s", (job_id,))
        conn.commit()

def poll_queue():
    print(f"Worker started. Retention Policy: {RETENTION_HOURS} hours.")
    
    # Initialize so it runs shortly after startup, not immediately
    last_cleanup = time.time()
    
    while True:
        try:
            conn = get_db_connection()
            
            # --- RUN JANITOR ---
            # Checks every CLEANUP_INTERVAL_SECONDS
            if time.time() - last_cleanup > CLEANUP_INTERVAL_SECONDS:
                cleanup_old_jobs(conn)
                last_cleanup = time.time()
            # -------------------

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM jobs 
                    WHERE status = 'QUEUED' 
                    ORDER BY created_at ASC 
                    LIMIT 1 
                    FOR UPDATE SKIP LOCKED
                """)
                job = cur.fetchone()
                
                if job:
                    cur.execute("UPDATE jobs SET status = 'PROCESSING' WHERE id = %s", (job['id'],))
                    conn.commit()
                    process_job(conn, job)
                else:
                    time.sleep(2)
            
            conn.close()
            
        except Exception as e:
            print(f"⚠️ DB Connection Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    time.sleep(8) 
    poll_queue()
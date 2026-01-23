const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const { Pool } = require('pg');
const router = express.Router();

const pool = new Pool({
  connectionString: process.env.DATABASE_URL
});

// Configure Shared Volume
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    const uploadDir = '/app/uploads';
    if (!fs.existsSync(uploadDir)) fs.mkdirSync(uploadDir, { recursive: true });
    cb(null, uploadDir);
  },
  filename: (req, file, cb) => {
    const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
    cb(null, 'job-' + uniqueSuffix + path.extname(file.originalname));
  }
});
const upload = multer({ storage: storage });


// UPLOAD: Starts the Queue
router.post('/upload', upload.single('pdf'), async (req, res) => {
  if (!req.file) return res.status(400).json({ error: 'No PDF provided' });

  try {
    const userId = req.user.id; 
    const outputDirName = req.file.filename.replace('.pdf', '');

    const query = `
      INSERT INTO jobs (user_id, input_file, output_dir, status)
      VALUES ($1, $2, $3, 'QUEUED')
      RETURNING id, status
    `;
    const result = await pool.query(query, [userId, req.file.filename, outputDirName]);
    
    console.log(`pb [API] Job Queued: ${result.rows[0].id}`);
    res.status(202).json({ jobId: result.rows[0].id, status: 'QUEUED' });

  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Database error' });
  }
});

// STATUS: Checks Job Progress (Polling)
router.get('/jobs/:id/status', async (req, res) => {
  try {
    const { id } = req.params;
    
    const result = await pool.query(
      'SELECT status, page_count FROM jobs WHERE id = $1 AND user_id = $2',
      [id, req.user.id]
    );

    if (result.rows.length === 0) return res.status(404).json({ error: 'Job not found' });
    
    const job = result.rows[0];

    // Handle Purged state
    if (job.status === 'PURGED') {
        return res.json({ 
            status: 'PURGED', 
            message: 'Data has been securely auto-deleted.',
            page_count: job.page_count
        });
    }

    res.json(job);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Server error' });
  }
});

// DOWNLOAD / RESULT: Returns the final JSON
router.get('/jobs/:id/result', async (req, res) => {
  try {
    // 1. DB Lookup (Verify ownership)
    const jobRes = await pool.query(
      'SELECT output_dir, status FROM jobs WHERE id = $1 AND user_id = $2',
      [req.params.id, req.user.id]
    );

    if (jobRes.rows.length === 0) {
        return res.status(404).json({ error: 'Job not found' });
    }

    // Check if files are gone
    if (jobRes.rows[0].status === 'PURGED') {
        return res.status(410).json({ error: 'File deleted due to retention policy.' });
    }

    const dirName = jobRes.rows[0].output_dir;
    const fullDirPath = path.join('/app/uploads', dirName);
    const fullFilePath = path.join(fullDirPath, 'document.json');

    // 2. File System Checks (Diagnostic)
    // If anything is missing, return a 500 JSON error to help debug.
    if (!fs.existsSync(fullDirPath)) {
        console.error(`[DEBUG] Missing Folder: ${fullDirPath}`);
        return res.status(500).json({ error: 'Output folder missing on disk' });
    }

    if (!fs.existsSync(fullFilePath)) {
        console.error(`[DEBUG] Missing File: ${fullFilePath}`);
        return res.status(500).json({ error: 'Result file missing on disk' });
    }

    // Success: Send the File
    res.sendFile(fullFilePath);

  } catch (err) {
    console.error("[DEBUG] CRASH:", err);
    res.status(500).json({ error: 'Internal Server Error' });
  }
});

module.exports = router;
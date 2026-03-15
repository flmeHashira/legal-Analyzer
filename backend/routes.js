const express = require("express");
const multer = require("multer");
const path = require("path");
const fs = require("fs");
const router = express.Router();

const pool = require("./db");


const MAX_FILE_SIZE_MB = parseInt(process.env.MAX_FILE_SIZE_MB) || 5;
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;
const USER_DAILY_DOC_LIMIT = parseInt(process.env.USER_DAILY_DOC_LIMIT) || 5;
const GLOBAL_DAILY_DOC_LIMIT = parseInt(process.env.GLOBAL_DAILY_DOC_LIMIT) || 900;

// Configure Shared Volume
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    const uploadDir = "/app/uploads";
    if (!fs.existsSync(uploadDir)) fs.mkdirSync(uploadDir, { recursive: true });
    cb(null, uploadDir);
  },
  filename: (req, file, cb) => {
    const uniqueSuffix = Date.now() + "-" + Math.round(Math.random() * 1e9);
    cb(null, "job-" + uniqueSuffix + path.extname(file.originalname));
  },
});

// File Size Limit Config
const upload = multer({ 
  storage: storage,
  limits: { fileSize: MAX_FILE_SIZE_BYTES } 
});
const uploadMiddleware = upload.single("pdf");

// UPLOAD: Starts the Queue with Limits
router.post("/upload", (req, res, next) => {
  uploadMiddleware(req, res, function (err) {
    if (err instanceof multer.MulterError) {
      if (err.code === 'LIMIT_FILE_SIZE') {
        return res.status(413).json({ error: `File too large. Maximum size is ${MAX_FILE_SIZE_MB}MB.` });
      }
      return res.status(400).json({ error: err.message });
    } else if (err) {
      return res.status(500).json({ error: 'File upload error' });
    }
    next();
  });
}, async (req, res) => {
  if (!req.file) return res.status(400).json({ error: "No PDF provided" });

  try {
    const userId = req.user.id;

    const globalQuotaCheck = await pool.query(
      `SELECT COUNT(*) FROM jobs WHERE created_at >= NOW() - INTERVAL '24 hours'`
    );
    const globalCount = parseInt(globalQuotaCheck.rows[0].count);

    if (globalCount >= GLOBAL_DAILY_DOC_LIMIT) {
      // Delete the file Multer just saved
      const fullPath = path.join("/app/uploads", req.file.filename);
      await fs.promises.unlink(fullPath).catch(() => {});
      
      return res.status(503).json({ 
        error: "Wow, we are experiencing unprecedented demand! Our daily free analysis quota has been reached. Please try again tomorrow." 
      });
    }

    // INDIVIDUAL USER RATE LIMITING
    const userQuotaCheck = await pool.query(
      `SELECT COUNT(*) FROM jobs 
       WHERE user_id = $1 AND created_at >= NOW() - INTERVAL '24 hours'`,
      [userId]
    );

    const docCount = parseInt(userQuotaCheck.rows[0].count);

    if (docCount >= USER_DAILY_DOC_LIMIT) {
      // Cleanup the file Multer just saved
      const fullPath = path.join("/app/uploads", req.file.filename);
      await fs.promises.unlink(fullPath).catch(() => {});
      
      return res.status(429).json({ 
        error: `Daily limit reached. You can only analyze ${USER_DAILY_DOC_LIMIT} documents per 24 hours.` 
      });
    }
    // -----------------------------------------------------

    const outputDirName = req.file.filename.replace(".pdf", "");
    const originalName = req.file.originalname; //Grab the real name from Multer

    const query = `
      INSERT INTO jobs (user_id, original_filename, input_file, output_dir, status)
      VALUES ($1, $2, $3, $4, 'QUEUED')
      RETURNING id, status
    `;

    // Add originalName to the array (matches $2)
    const result = await pool.query(query, [
      userId,
      originalName,
      req.file.filename,
      outputDirName,
    ]);

    console.log(`[API] Job Queued: ${result.rows[0].id}`);
    res.status(202).json({ jobId: result.rows[0].id, status: "QUEUED" });
  } catch (err) {
    console.error(err);
    // Cleanup file on DB error
    if (req.file) {
      await fs.promises.unlink(path.join('/app/uploads', req.file.filename)).catch(() => {});
    }
    res.status(500).json({ error: "Database error" });
  }
});

// GET ALL JOBS: Populates the Home Page Feed
router.get("/jobs", async (req, res) => {
  try {
    const result = await pool.query(
      "SELECT id, original_filename, input_file, status, page_count, created_at FROM jobs WHERE user_id = $1 ORDER BY created_at DESC",
      [req.user.id],
    );
    res.json(result.rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to fetch jobs" });
  }
});

// STATUS: Checks Job Progress (Polling)
router.get("/jobs/:id/status", async (req, res) => {
  try {
    const { id } = req.params;

    const result = await pool.query(
      "SELECT status, page_count FROM jobs WHERE id = $1 AND user_id = $2",
      [id, req.user.id],
    );

    if (result.rows.length === 0)
      return res.status(404).json({ error: "Job not found" });

    const job = result.rows[0];

    // Handle Purged state
    if (job.status === "PURGED") {
      return res.json({
        status: "PURGED",
        message: "Data has been securely auto-deleted.",
        page_count: job.page_count,
      });
    }

    res.json(job);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Server error" });
  }
});

// DOWNLOAD / RESULT: Returns the final JSON
router.get("/jobs/:id/result", async (req, res) => {
  try {
    // 1. DB Lookup (Verify ownership)
    const jobRes = await pool.query(
      "SELECT output_dir, status FROM jobs WHERE id = $1 AND user_id = $2",
      [req.params.id, req.user.id],
    );

    if (jobRes.rows.length === 0) {
      return res.status(404).json({ error: "Job not found" });
    }

    // Check if files are gone
    if (jobRes.rows[0].status === "PURGED") {
      return res
        .status(410)
        .json({ error: "File deleted due to retention policy." });
    }

    const dirName = jobRes.rows[0].output_dir;
    const fullDirPath = path.join("/app/uploads", dirName);
    const fullFilePath = path.join(fullDirPath, "document.json");

    // 2. File System Checks (Diagnostic)
    if (!fs.existsSync(fullDirPath)) {
      console.error(`[DEBUG] Missing Folder: ${fullDirPath}`);
      return res.status(500).json({ error: "Output folder missing on disk" });
    }

    if (!fs.existsSync(fullFilePath)) {
      console.error(`[DEBUG] Missing File: ${fullFilePath}`);
      return res.status(500).json({ error: "Result file missing on disk" });
    }

    // Success: Send the File
    res.sendFile(fullFilePath);
  } catch (err) {
    console.error("[DEBUG] CRASH:", err);
    res.status(500).json({ error: "Internal Server Error" });
  }
});

// DOWNLOAD: Returns the redaction map
router.get('/jobs/:id/redaction-map', async (req, res) => {
  try {
    const jobRes = await pool.query(
      'SELECT output_dir, status FROM jobs WHERE id = $1 AND user_id = $2',
      [req.params.id, req.user.id]
    );

    if (jobRes.rows.length === 0) return res.status(404).json({ error: 'Job not found' });
    if (jobRes.rows[0].status === 'PURGED') return res.status(410).json({ error: 'File deleted.' });

    const fullFilePath = path.join('/app/uploads', jobRes.rows[0].output_dir, 'redaction_map.json');

    if (!fs.existsSync(fullFilePath)) {
        return res.json({}); 
    }

    res.sendFile(fullFilePath);

  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Server Error' });
  }
});

// SERVE THE PDF FILE
router.get("/jobs/:id/pdf", async (req, res) => {
  try {
    const jobRes = await pool.query(
      "SELECT input_file, status FROM jobs WHERE id = $1 AND user_id = $2",
      [req.params.id, req.user.id],
    );

    if (jobRes.rows.length === 0) {
      return res.status(404).json({ error: "Job not found" });
    }

    if (jobRes.rows[0].status === "PURGED") {
      return res
        .status(410)
        .json({ error: "File deleted due to retention policy." });
    }

    const fileName = jobRes.rows[0].input_file;
    const filePath = path.join("/app/uploads", fileName);

    if (!fs.existsSync(filePath)) {
      console.error(`[DEBUG] Missing PDF File: ${filePath}`);
      return res.status(500).json({ error: "PDF missing on disk" });
    }

    res.contentType("application/pdf");
    res.sendFile(filePath);
  } catch (err) {
    console.error("[DEBUG] CRASH:", err);
    res.status(500).json({ error: "Internal Server Error" });
  }
});

//Delete one item
router.delete("/jobs/:id", async (req, res) => {
  try {
    const { id } = req.params;
    const userId = req.user.id;

    const result = await pool.query(
      "SELECT output_dir FROM jobs WHERE id = $1 AND user_id = $2",
      [id, userId],
    );

    if (result.rows.length === 0)
      return res.status(404).json({ error: "Job not found" });

    const { output_dir } = result.rows[0];
    const UPLOAD_ROOT = "/app/uploads";

    const folderPath = path.join(UPLOAD_ROOT, output_dir);
    const pdfPath = path.join(UPLOAD_ROOT, `${output_dir}.pdf`);

    try {
      await fs.promises.rm(folderPath, { recursive: true, force: true });
      console.log(`🗑️ Deleted Folder: ${folderPath}`);
    } catch (e) {
      console.warn(`⚠️ Folder already gone or busy: ${folderPath}`);
    }

    try {
      await fs.promises.unlink(pdfPath);
      console.log(`🗑️ Deleted PDF: ${pdfPath}`);
    } catch (e) {
      console.warn(`⚠️ PDF already gone or busy: ${pdfPath}`);
    }

    await pool.query("DELETE FROM jobs WHERE id = $1 AND user_id = $2", [
      id,
      userId,
    ]);

    res.json({ message: "Success" });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Server error" });
  }
});

module.exports = router;
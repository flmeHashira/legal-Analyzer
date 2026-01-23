// backend/index.js
const express = require('express');
const cors = require('cors');
const authMiddleware = require('./auth');
const jobRoutes = require('./routes');

const app = express();
const port = 3000;

app.use(cors());
app.use(express.json());

app.use('/api', authMiddleware);

// Routes (Mounts /upload, /status, /result, /vault)
app.use('/api', jobRoutes); 

app.get('/', (req, res) => {
  res.send('Legal Analyzer API is running...');
});

app.listen(port, () => {
  console.log(`Backend running on ${port}`);
});
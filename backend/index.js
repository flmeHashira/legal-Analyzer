const express = require('express');
const cors = require('cors');
const cookieParser = require('cookie-parser');
const authMiddleware = require('./auth');
const jobRoutes = require('./routes');
const authRoutes = require('./authRoutes');

const app = express();
const port = 3000;

app.use(cors({
  origin: 'http://localhost:5173', // Must match Frontend URL exactly
  credentials: true  // Allows the browser to send the HttpOnly Cookie
}));

app.use(express.json());
app.use(cookieParser());

// Public Auth Routes (Login, Register)
app.use('/api/auth', authRoutes);

// Protected Routes (Upload/Status/Result)
app.use('/api', authMiddleware, jobRoutes);


app.get('/', (req, res) => {
  res.send('Legal Analyzer API is running...');
});

app.listen(port, () => {
  console.log(`Backend running on ${port}`);
});
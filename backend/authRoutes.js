const express = require('express');
const router = express.Router();
const bcrypt = require('bcryptjs');
const pool = require('./db');
const jwt = require('jsonwebtoken');

const isProduction = process.env.NODE_ENV === 'production';

router.post('/login', async (req, res) => {
    const { email, password } = req.body;

    if (!email || !password) {
      return res.status(400).json({ error: "Email and password are required" });
    }

    try {
        const result = await pool.query(
            'SELECT * FROM users WHERE email = $1', 
            [email]
        );

        if (result.rows.length === 0) {
            return res.status(400).json({ error: "Invalid credentials" }); 
        }

        const user = result.rows[0];
        const isMatch = await bcrypt.compare(password, user.password_hash);
        
        if (!isMatch) {
            return res.status(400).json({ error: "Invalid credentials" }); 
        }

        const token = jwt.sign(
            { id: user.id }, 
            process.env.JWT_SECRET, 
            { expiresIn: '4h' }
        );

        res.cookie('token', token, { 
            httpOnly: true, 
            secure: isProduction, // true in Prod, false in Dev
            sameSite: 'Strict', 
            maxAge: 4 * 60 * 60 * 1000 // 4 hours
        });

        res.status(200).json({ 
            message: "Login successful", 
            email: user.email
        });

    } catch (err) {
        console.error("Login Error:", err);
        res.status(500).json({ error: "Server error" });
    }
});

router.post('/logout', (req, res) => {
    res.clearCookie('token');   // Deletes the cookie
    res.json({ message: "Logged out" });
});

router.post('/register', async (req, res) => {
    const { email, password } = req.body;

    if (!email || !password) {
      return res.status(400).json({ error: "Email and password are required" });
    }

    try {
        const salt = await bcrypt.genSalt(10);
        const hashedPassword = await bcrypt.hash(password, salt);

        const newUser = await pool.query(
            'INSERT INTO users (email, password_hash) VALUES ($1, $2) RETURNING id, email',
            [email, hashedPassword]
        );
        
        console.log("Created user:", newUser.rows[0]);
        res.status(201).json({ 
            message: "User created successfully",
            user: newUser.rows[0] 
        });

    } catch (err) {
        if (err.code === '23505') { 
            return res.status(409).json({ error: 'User already exists' });
        }
        console.error("Register Error:", err);
        res.status(500).json({ error: 'Database error' });
    }
});

router.get('/me', async (req, res) => {
    const token = req.cookies.token; 

    if (!token) {
        // Return 401 so the frontend AuthContext knows to stay "Logged Out"
        return res.status(401).json({ error: "Not authenticated" });
    }

    try {
        const user = jwt.verify(token, process.env.JWT_SECRET);
        res.status(200).json(user);

    } catch (err) {
        // If token is tampered with or expired, return 401
        return res.status(401).json({ error: "Invalid token" });
    }
});

module.exports = router;
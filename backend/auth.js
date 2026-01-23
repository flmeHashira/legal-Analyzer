const jwt = require('jsonwebtoken');

function authMiddleware(req, res, next) {
  // DEV MODE BYPASS (Strict)
  if (process.env.NODE_ENV === 'development') {
    // SECURITY CHECK: Ensure the ID actually exists in the Environment
    const devUserId = process.env.DEV_USER_ID;
    
    if (!devUserId) {
      console.error('FATAL: NODE_ENV is development, but DEV_USER_ID is missing!');
      // Fail Fast: Crash or returning 500 is safer than guessing
      return res.status(500).json({ error: 'Server Misconfiguration' }); 
    }

    req.user = { id: devUserId, email: 'dev@local' };
    return next();
  }

  // PRODUCTION CHECK
  const authHeader = req.headers['authorization'];
  const token = authHeader && authHeader.split(' ')[1];

  if (!token) return res.sendStatus(401);

  jwt.verify(token, process.env.JWT_SECRET, (err, user) => {
    if (err) return res.sendStatus(403);
    req.user = user;
    next();
  });
}

module.exports = authMiddleware;
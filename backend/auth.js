const jwt = require('jsonwebtoken');

function authMiddleware(req, res, next) {
  // DEV MODE BYPASS (Strict)
  // if (process.env.NODE_ENV === 'development') {
  //   // SECURITY CHECK: Ensure the ID actually exists in the Environment
  //   const devUserId = process.env.DEV_USER_ID;
    
  //   if (!devUserId) {
  //     console.error('FATAL: NODE_ENV is development, but DEV_USER_ID is missing!');
  //     // Fail Fast: Crash or returning 500 is safer than guessing
  //     return res.status(500).json({ error: 'Server Misconfiguration' }); 
  //   }

  //   req.user = { id: devUserId, email: 'dev@local' };
  //   return next();
  // }

  // 2. PRODUCTION CHECK (Cookie-Based)
  const token = req.cookies.token; 

  if (!token) return res.status(401).json({ error: "Authentication required" });

  jwt.verify(token, process.env.JWT_SECRET, (err, user) => {
    if (err) {
        // Clean up the bad cookie so the browser doesn't keep sending it
        res.clearCookie('token'); 
        return res.status(403).json({ error: "Token invalid or expired" });
    }
    
    req.user = user;
    next();
  });
}

module.exports = authMiddleware;
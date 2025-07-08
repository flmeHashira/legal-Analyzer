const express = require("express");
const app = express();
app.get("/", (_, res) => res.send("Backend upp"));
app.listen(3000, () => console.log("Backend running on 3000"));
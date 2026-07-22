const bcrypt = require('bcryptjs');
const hash = "$2b$12$W9zFHw7M0Jem5gWMoo7jf.ZmuXAEUL2k4sEYHisbl9EaObS/JN6sW";
const passwords = ["admin", "password", "jenex", "leadscope", "jenex_dev", "leadscope_dev", "admin_dev"];
(async () => {
  for (const p of passwords) {
    if (await bcrypt.compare(p, hash)) {
      console.log("MATCH FOUND:", p);
      return;
    }
  }
  console.log("NO MATCH");
})();

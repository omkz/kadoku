// Seed a local Better Auth administrator through Better Auth's password hasher.
// Invoked by: cd apps/api && uv run python -m app.db seed
import { randomBytes } from "node:crypto";
import { betterAuth } from "better-auth";
import pg from "pg";

const urlString = process.env.AUTH_DATABASE_URL;
const expectedName = process.env.KADOKU_EXPECTED_DB_NAME;
if (!urlString || !expectedName) throw new Error("Missing local DB configuration");
const url = new URL(urlString);
const dbName = decodeURIComponent(url.pathname.slice(1));
if (
  !["postgres:", "postgresql:"].includes(url.protocol) ||
  !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname) ||
  dbName !== expectedName ||
  !["kadoku", "kadoku_test"].includes(dbName)
) {
  throw new Error("Refusing to seed an admin outside the selected local Kadoku database");
}
if (!process.env.BETTER_AUTH_SECRET) {
  throw new Error("Set BETTER_AUTH_SECRET in apps/web/.env");
}

const email = "admin@kadoku.local";
const pool = new pg.Pool({ connectionString: urlString });
const auth = betterAuth({
  database: pool,
  secret: process.env.BETTER_AUTH_SECRET,
  baseURL: process.env.BETTER_AUTH_URL || "http://localhost:3000",
  emailAndPassword: { enabled: true, minPasswordLength: 8 },
});

try {
  const existing = await pool.query('SELECT id, role FROM "user" WHERE lower(email) = $1', [email]);
  let userId;
  if (existing.rowCount) {
    userId = existing.rows[0].id;
    console.log("Existing development admin found; password left unchanged.");
  } else {
    const password = randomBytes(20).toString("base64url");
    const created = await auth.api.signUpEmail({
      body: { email, password, name: "Kadoku Dev Admin" },
    });
    userId = created.user.id;
    console.log("Development admin created.");
    console.log(`Email: ${email}`);
    console.log(`Password (save now): ${password}`);
  }
  await pool.query('UPDATE "user" SET role = $1 WHERE id = $2', ["admin", userId]);
  console.log(`Admin access ready: ${email}`);
} finally {
  await pool.end();
}

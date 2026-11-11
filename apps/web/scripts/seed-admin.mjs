// Seed a local Better Auth administrator through Better Auth's password hasher.
// Invoked by: cd apps/api && uv run python -m app.db seed
import { betterAuth } from "better-auth";
import pg from "pg";

const urlString = process.env.AUTH_DATABASE_URL;
const expectedName = process.env.KADOKU_EXPECTED_DB_NAME;
const expectedPort = process.env.KADOKU_EXPECTED_DB_PORT || "5432";
if (!urlString || !expectedName) throw new Error("Missing local DB configuration");
const url = new URL(urlString);
const dbName = decodeURIComponent(url.pathname.slice(1));
if (
  !["postgres:", "postgresql:"].includes(url.protocol) ||
  !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname) ||
  dbName !== expectedName ||
  (url.port || "5432") !== expectedPort ||
  !["kadoku", "kadoku_test"].includes(dbName)
) {
  throw new Error("Refusing to seed an admin outside the selected local Kadoku database");
}
if (!process.env.BETTER_AUTH_SECRET) {
  throw new Error("Set BETTER_AUTH_SECRET in apps/web/.env");
}

if (process.argv.includes("--check")) {
  console.log("Verified local Better Auth database configuration.");
  process.exit(0);
}

const email = (process.env.DEV_ADMIN_EMAIL || "").trim().toLowerCase();
const password = process.env.DEV_ADMIN_PASSWORD || "";
if (!email || !email.includes("@") || password.length < 8) {
  throw new Error("Set DEV_ADMIN_EMAIL and DEV_ADMIN_PASSWORD (at least 8 characters) in apps/web/.env");
}

// One customer account; My People (including Mom) belongs to this customer.
const customer = { name: "Nadia", email: "nadia@kadoku.test" };

const pool = new pg.Pool({ connectionString: urlString });
const auth = betterAuth({
  database: pool,
  secret: process.env.BETTER_AUTH_SECRET,
  baseURL: process.env.BETTER_AUTH_URL || "http://localhost:3000",
  emailAndPassword: { enabled: true, minPasswordLength: 8 },
});

async function ensureAccount(accountEmail, name, role) {
  const found = await pool.query(
    'SELECT id, role FROM "user" WHERE lower(email) = $1',
    [accountEmail],
  );
  let id;
  if (found.rowCount) {
    id = found.rows[0].id;
    if (role === "user" && found.rows[0].role && found.rows[0].role !== "user") {
      throw new Error("A seeded customer email already belongs to a privileged account");
    }
  } else {
    const created = await auth.api.signUpEmail({
      body: { email: accountEmail, password, name },
    });
    id = created.user.id;
  }
  if (role === "admin") {
    await pool.query('UPDATE "user" SET role = $1 WHERE id = $2', ["admin", id]);
  } else {
    await pool.query('UPDATE "user" SET role = $1 WHERE id = $2', ["user", id]);
  }
  return id;
}

try {
  const adminId = await ensureAccount(email, "Kadoku Admin", "admin");
  console.log(`Admin ready: ${email}`);
  console.log(`SEED_ADMIN_USER_ID=${adminId}`);
  if (customer.email === email) {
    throw new Error("DEV_ADMIN_EMAIL must differ from the customer email");
  }
  const customerId = await ensureAccount(customer.email, customer.name, "user");
  console.log(`Customer ready: ${customer.name} (${customer.email})`);
  console.log(`SEED_CUSTOMER_USER_ID=${customerId}`);
  console.log("Customer password uses DEV_ADMIN_PASSWORD (local development only).");
} finally {
  await pool.end();
}

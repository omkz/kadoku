#!/usr/bin/env node
import {resolve} from "node:path";
import {pathToFileURL} from "node:url";
import pg from "pg";
import {betterAuth} from "better-auth";
import {admin} from "better-auth/plugins";

const {Pool} = pg;
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);
const usage = [
  "Usage: pnpm admin:create [--role admin|super_admin] [--email EMAIL] [--name NAME]",
  "Defaults to super_admin and reads DEV_SUPER_ADMIN_EMAIL/PASSWORD from apps/web/.env.",
  "For --role admin, reads DEV_ADMIN_EMAIL/PASSWORD. Local development only.",
].join("\n");

export function readConfig(args, env) {
  if (args.includes("--help") || args.includes("-h")) return null;
  const options = {role:"super_admin", email:"", name:""};
  for (let i=0; i<args.length; i++) {
    const key = args[i];
    if (!["--email", "--role", "--name"].includes(key)) {
      throw new Error("Unknown argument: " + key);
    }
    if (!args[i+1] || args[i+1].startsWith("--")) {
      throw new Error("Missing value for " + key);
    }
    options[key.slice(2)] = args[++i];
  }
  if (!["admin", "super_admin"].includes(options.role)) {
    throw new Error("Role must be admin or super_admin");
  }
  const prefix = options.role === "super_admin" ? "DEV_SUPER_ADMIN" : "DEV_ADMIN";
  options.email = (options.email || env[prefix + "_EMAIL"] || "").trim().toLowerCase();
  options.name = (options.name || env[prefix + "_NAME"] ||
    (options.role === "super_admin" ? "Super Admin" : "Admin")).trim();
  const password = env[prefix + "_PASSWORD"] || "";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(options.email)) {
    throw new Error("Set " + prefix + "_EMAIL in apps/web/.env");
  }
  if (options.name.length < 1 || options.name.length > 120) {
    throw new Error("Account name must be 1–120 characters");
  }
  if (password.length < 16 || password.length > 128) {
    throw new Error("Set " + prefix + "_PASSWORD (16–128 characters) in apps/web/.env");
  }
  return {...options, password};
}

export function validateLocalTarget(env) {
  if (env.NODE_ENV === "production" || env.ENVIRONMENT === "production") {
    throw new Error("admin:create is disabled in production");
  }
  if (!env.AUTH_DATABASE_URL) throw new Error("AUTH_DATABASE_URL is required");
  if (!env.BETTER_AUTH_SECRET || env.BETTER_AUTH_SECRET.length < 32) {
    throw new Error("BETTER_AUTH_SECRET must contain at least 32 characters");
  }
  const db = new URL(env.AUTH_DATABASE_URL);
  if (!["postgres:", "postgresql:"].includes(db.protocol) ||
      !LOCAL_HOSTS.has(db.hostname) || !db.pathname || db.pathname === "/") {
    throw new Error("admin:create requires a local PostgreSQL database");
  }
  const authUrl = new URL(env.BETTER_AUTH_URL || "http://localhost:3000");
  if (authUrl.protocol !== "http:" || !LOCAL_HOSTS.has(authUrl.hostname) ||
      authUrl.username || authUrl.password || authUrl.search || authUrl.hash ||
      authUrl.pathname !== "/") {
    throw new Error("admin:create requires a local http://localhost Better Auth URL");
  }
}

async function main() {
  const options = readConfig(process.argv.slice(2), process.env);
  if (options === null) {console.log(usage); return;}
  validateLocalTarget(process.env);

  const pool = new Pool({connectionString:process.env.AUTH_DATABASE_URL});
  let createdUserId = null;
  try {
    const auth = betterAuth({
      database:pool,
      secret:process.env.BETTER_AUTH_SECRET,
      baseURL:process.env.BETTER_AUTH_URL || "http://localhost:3000",
      emailAndPassword:{
        enabled:true, minPasswordLength:8, autoSignIn:false,
        customSyntheticUser:({coreFields, additionalFields, id}) => ({
          ...coreFields, role:"user", banned:false,
          banReason:null, banExpires:null, ...additionalFields, id,
        }),
      },
      plugins:[admin({defaultRole:"user"})],
    });

    const existing = await pool.query(
      'SELECT id, role, banned FROM "user" WHERE lower(email) = $1 LIMIT 1',
      [options.email]
    );
    if (existing.rowCount) {
      const user = existing.rows[0];
      if (user.banned || user.role !== options.role) {
        throw new Error("Account exists with a different role or is banned; leaving it unchanged");
      }
      // Re-running the command must not silently accept a different password.
      const signedIn = await auth.api.signInEmail({
        body:{email:options.email, password:options.password, rememberMe:false},
      });
      if (signedIn?.user?.id !== user.id) {
        throw new Error("Existing account could not be verified");
      }
      console.log("Account already exists with role " + options.role + "; verified, unchanged.");
      return;
    }

    // Better Auth creates and hashes the password; never insert into auth tables.
    const signedUp = await auth.api.signUpEmail({
      body:{email:options.email, name:options.name, password:options.password},
    });
    createdUserId = signedUp?.user?.id;
    if (!createdUserId) throw new Error("Better Auth did not return a new user ID");

    const result = await pool.query(
      'UPDATE "user" SET role = $1 WHERE id = $2 AND lower(email) = $3 ' +
      "AND (role = 'user' OR role IS NULL) AND (banned IS NULL OR banned = false) RETURNING id",
      [options.role, createdUserId, options.email]
    );
    if (result.rowCount !== 1) throw new Error("Could not assign the requested role");
    console.log("Created " + options.email + " with role " + options.role + ".");
    console.log("Sign in with the account to access Kadoku admin.");
  } catch (error) {
    if (createdUserId) {
      console.error("Account may have been created without its role; check it before retrying.");
    }
    throw error;
  } finally {
    await pool.end();
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch(error => {
    console.error("admin:create: " + (error instanceof Error ? error.message : String(error)));
    process.exitCode = 1;
  });
}

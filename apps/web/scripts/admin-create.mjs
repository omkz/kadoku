#!/usr/bin/env node
// Explicit operator-only account provisioning. Never import this from the app.
import {stdin, stdout} from "node:process";
import {emitKeypressEvents} from "node:readline";
import {Pool} from "pg";
import {betterAuth} from "better-auth";
import {admin} from "better-auth/plugins";

const usage = [
  "Usage: pnpm admin:create --email EMAIL --role admin|super_admin --confirm",
  'Optional: --name "Display Name"',
  "Run from a trusted local shell in apps/web; password is prompted, not passed in arguments.",
].join("\n");

function parseArgs(args) {
  const options = {email:"", role:"", name:"", confirm:false};
  for (let i=0; i<args.length; i++) {
    const key = args[i];
    if (key === "--help" || key === "-h") return null;
    if (key === "--confirm") {options.confirm = true; continue;}
    if (!["--email", "--role", "--name"].includes(key)) throw new Error("Unknown argument: " + key);
    if (!args[i+1] || args[i+1].startsWith("--")) throw new Error("Missing value for " + key);
    options[key.slice(2)] = args[++i];
  }
  options.email = options.email.trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(options.email)) throw new Error("Provide a valid --email");
  if (!["admin", "super_admin"].includes(options.role)) throw new Error("Specify --role admin or --role super_admin");
  if (!options.confirm) throw new Error("Pass --confirm to authorize this privileged account creation");
  options.name = options.name.trim() || (options.role === "super_admin" ? "Super Admin" : "Admin");
  if (options.name.length > 120) throw new Error("Name must be at most 120 characters");
  return options;
}

function secretPrompt(label) {
  if (!stdin.isTTY || !stdout.isTTY || typeof stdin.setRawMode !== "function") {
    throw new Error("An interactive terminal is required for secure password entry");
  }
  emitKeypressEvents(stdin);
  const wasRaw = Boolean(stdin.isRaw);
  stdin.setRawMode(true);
  stdin.resume();
  stdout.write(label);
  return new Promise((resolve, reject) => {
    let secret = "";
    function finish(value, error) {
      stdin.off("keypress", onKey);
      stdin.setRawMode(wasRaw);
      stdin.pause();
      stdout.write("\n");
      if (error) reject(error);
      else resolve(value);
    }
    function onKey(char, key) {
      if (key?.ctrl && key.name === "c") return finish(null, new Error("Cancelled"));
      if (key?.name === "return" || key?.name === "enter") return finish(secret);
      if (key?.name === "backspace" || key?.name === "delete") {
        secret = secret.slice(0, -1);
      } else if (typeof char === "string" && char && !key?.ctrl && !key?.meta &&
                 !/[\u0000-\u001f\u007f]/u.test(char)) {
        secret += char;
      }
    }
    stdin.on("keypress", onKey);
  });
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (!options) {console.log(usage); return;}
  if (process.env.ENVIRONMENT === "production" || process.env.NODE_ENV === "production") {
    throw new Error("This local provisioning command is disabled in production");
  }
  if (!process.env.AUTH_DATABASE_URL) throw new Error("Configure AUTH_DATABASE_URL in apps/web/.env");
  if (!process.env.BETTER_AUTH_SECRET || process.env.BETTER_AUTH_SECRET.length < 32) {
    throw new Error("Configure a BETTER_AUTH_SECRET of at least 32 characters");
  }

  const pool = new Pool({connectionString:process.env.AUTH_DATABASE_URL});
  let created = false;
  try {
    const existing = await pool.query(
      'SELECT id FROM "user" WHERE lower(email) = $1 LIMIT 1', [options.email]
    );
    if (existing.rowCount) throw new Error("User already exists; CLI will not change existing roles");

    const password = await secretPrompt("Password (at least 12 characters): ");
    const repeated = await secretPrompt("Confirm password: ");
    if (password.length < 12) throw new Error("Password must contain at least 12 characters");
    if (password !== repeated) throw new Error("Passwords do not match");

    // Better Auth creates the account and hashes the password using its normal flow.
    const auth = betterAuth({
      database: pool,
      secret: process.env.BETTER_AUTH_SECRET,
      baseURL: process.env.BETTER_AUTH_URL || "http://localhost:3000",
      emailAndPassword: {enabled:true, minPasswordLength:8},
      plugins: [admin({defaultRole:"user"})],
    });
    const signup = await auth.api.signUpEmail({
      body: {email:options.email, password, name:options.name},
    });
    if (!signup?.user?.id) throw new Error("Better Auth did not return a new user ID");
    created = true;

    // Role changes are DB-backed in Kadoku; no admin API permission is exposed.
    const promoted = await pool.query(
      'UPDATE "user" SET role = $1 WHERE id = $2 AND lower(email) = $3 RETURNING id',
      [options.role, signup.user.id, options.email]
    );
    if (promoted.rowCount !== 1) throw new Error("Could not assign role to the new account");
    console.log("Created " + options.email + " with role " + options.role + ".");
    console.log("Sign in with that account to use Kadoku admin.");
  } catch (error) {
    if (created) console.error("Account created, but role assignment failed. Verify the account before retrying.");
    throw error;
  } finally {
    await pool.end();
  }
}

main().catch(error => {
  console.error("admin:create: " + (error instanceof Error ? error.message : String(error)));
  process.exitCode = 1;
});

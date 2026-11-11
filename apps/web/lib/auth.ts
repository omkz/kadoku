import { betterAuth } from "better-auth";
import { admin, jwt } from "better-auth/plugins";
import {ac, roles} from "./auth-roles";
import { Pool } from "pg";

const pool = new Pool({connectionString: process.env.AUTH_DATABASE_URL});

export const auth = betterAuth({
  database: pool,
  secret: process.env.BETTER_AUTH_SECRET,
  baseURL: process.env.BETTER_AUTH_URL || "http://localhost:3000",
  emailAndPassword: { enabled: true, minPasswordLength: 8 },
  socialProviders: process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET ? {
    google: {
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
      requireEmailVerification: true,
    },
  } : {},
  plugins: [admin({ac, roles, defaultRole:"user", adminRoles:["admin","super_admin"]}), jwt({jwks: {keyPairConfig: {alg: "EdDSA", crv: "Ed25519"}}})],
});

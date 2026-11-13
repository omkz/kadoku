import assert from "node:assert/strict";
import test from "node:test";
import {readConfig, validateLocalTarget} from "./admin-create.mjs";

const config = {
  DEV_SUPER_ADMIN_EMAIL:"superadmin@kadoku.test",
  DEV_SUPER_ADMIN_PASSWORD:"a-different-unique-password",
  DEV_ADMIN_EMAIL:"admin@kadoku.test",
  DEV_ADMIN_PASSWORD:"another-unique-password",
};

const target = {
  AUTH_DATABASE_URL:"postgresql://kadoku:secret@localhost:5432/kadoku",
  BETTER_AUTH_SECRET:"a-secret-that-is-at-least-32-characters",
  BETTER_AUTH_URL:"http://localhost:3000",
};

test("no flags uses local .env super-admin credentials", () => {
  const options = readConfig([], config);
  assert.equal(options.email, "superadmin@kadoku.test");
  assert.equal(options.role, "super_admin");
  assert.equal(options.password, config.DEV_SUPER_ADMIN_PASSWORD);
});

test("admin role uses separate env credentials", () => {
  const options = readConfig(["--role", "admin"], config);
  assert.equal(options.email, "admin@kadoku.test");
  assert.equal(options.role, "admin");
  assert.equal(options.password, config.DEV_ADMIN_PASSWORD);
});

test("password and email must be explicitly configured", () => {
  assert.throws(() => readConfig([], {}), /DEV_SUPER_ADMIN_EMAIL/);
  assert.throws(() => readConfig([], {...config, DEV_SUPER_ADMIN_PASSWORD:"short"}), /DEV_SUPER_ADMIN_PASSWORD/);
  assert.throws(() => readConfig(["--confirm"], config), /Unknown argument/);
});

test("help works without environment configuration", () => {
  assert.equal(readConfig(["--help"], {}), null);
});

test("reject production and non-local databases", () => {
  assert.doesNotThrow(() => validateLocalTarget(target));
  assert.throws(() => validateLocalTarget({...target, NODE_ENV:"production"}), /disabled in production/);
  assert.throws(() => validateLocalTarget({...target, AUTH_DATABASE_URL:"postgresql://example.com/kadoku"}), /local PostgreSQL/);
  assert.throws(() => validateLocalTarget({...target, BETTER_AUTH_URL:"https://kadoku.example.com"}), /local http/);
});

import { createAccessControl } from "better-auth/plugins/access";
import { defaultStatements } from "better-auth/plugins/admin/access";

// Better Auth manages identity/role storage. Kadoku's business authorization is
// checked by FastAPI against the authoritative database on every admin request.
// Do not enable Better Auth's powerful built-in user CRUD/impersonation endpoints.
export const ac = createAccessControl(defaultStatements);
export const roles = {
  user: ac.newRole({}),
  admin: ac.newRole({}),
  super_admin: ac.newRole({}),
};

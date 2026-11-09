import { createAuthClient } from "better-auth/react";
import { jwtClient } from "better-auth/client/plugins";

export const authClient = createAuthClient({plugins: [jwtClient()]});

export async function authHeaders(required = false): Promise<Record<string, string>> {
  try {
    const {data, error} = await authClient.token();
    if (error || !data?.token) {
      if (required) throw new Error("Your session has expired. Please sign in again.");
      return {};
    }
    return {Authorization: `Bearer ${data.token}`};
  } catch {
    if (required) throw new Error("Unable to verify your session. Please sign in again.");
    return {};
  }
}

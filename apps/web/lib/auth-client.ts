import { createAuthClient } from "better-auth/react";
import { jwtClient } from "better-auth/client/plugins";

export const authClient = createAuthClient({plugins: [jwtClient()]});

export async function authHeaders(): Promise<Record<string, string>> {
  try {
    const {data} = await authClient.token();
    return data?.token ? {Authorization: `Bearer ${data.token}`} : {};
  } catch {
    return {};
  }
}

import {cookies} from "next/headers";
import {createHmac, randomUUID, timingSafeEqual} from "node:crypto";
import {NextResponse} from "next/server";

function signed(id: string, secret: string) {
  return createHmac("sha256",secret).update(id).digest("hex");
}

export async function GET() {
  const secret = process.env.GUEST_COOKIE_SECRET;
  if (!secret || secret.length < 32) return NextResponse.json({error:"Guest session is not configured"},{status:503});
  const cookieStore = await cookies();
  const previous = cookieStore.get("kadoku_guest")?.value || "";
  const [oldId,oldSignature] = previous.split(".");
  let id: string = randomUUID();
  if (oldId && /^[a-f0-9-]{36}$/i.test(oldId) && oldSignature && /^[a-f0-9]{64}$/i.test(oldSignature)) {
    const expected = Buffer.from(signed(oldId,secret),"hex");
    const actual = Buffer.from(oldSignature,"hex");
    if (expected.length === actual.length && timingSafeEqual(expected,actual)) id=oldId;
  }
  const token = `${id}.${signed(id,secret)}`;
  const result = NextResponse.json({guest:true});
  result.cookies.set("kadoku_guest",token,{httpOnly:true,secure:process.env.NODE_ENV==="production",sameSite:"lax",path:"/",maxAge:60*60*24*180});
  return result;
}

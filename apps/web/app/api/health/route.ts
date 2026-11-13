import {NextResponse} from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const response = await fetch("http://127.0.0.1:8000/api/health", {
      cache: "no-store",
      signal: AbortSignal.timeout(2000),
    });
    if (!response.ok) throw new Error("API is unhealthy");
    return NextResponse.json({status: "ok", web: "ok", api: "ok"});
  } catch {
    return NextResponse.json({status: "unavailable"}, {status: 503});
  }
}

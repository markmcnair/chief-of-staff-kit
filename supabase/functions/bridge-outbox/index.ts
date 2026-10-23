// bridge-outbox: the only door the Mac bridge has into the outbox.
// Actions (POST JSON, header x-bridge-secret): fetch | claim | finish.
// Deploy: supabase functions deploy bridge-outbox --no-verify-jwt
// Secrets: supabase secrets set BRIDGE_SECRET=...   (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are injected automatically)
import { createClient } from "npm:@supabase/supabase-js@2";

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, {
  db: { schema: "bridge" },
});
const json = (b: unknown, status = 200) =>
  new Response(JSON.stringify(b), { status, headers: { "Content-Type": "application/json" } });

function safeEqual(a: string, b: string) {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return json({ error: "method" }, 405);
  const secret = Deno.env.get("BRIDGE_SECRET") ?? "";
  if (!secret || !safeEqual(req.headers.get("x-bridge-secret") ?? "", secret)) return json({ error: "unauthorized" }, 401);
  const body = await req.json().catch(() => ({}));

  if (body.action === "fetch") {
    const limit = Math.min(Number(body.limit) || 5, 20);
    const { data, error } = await db.from("outbox").select("id").eq("status", "approved").order("id").limit(limit);
    return error ? json({ error: error.message }, 500) : json({ rows: data });
  }
  if (body.action === "claim") {
    const { data, error } = await db.rpc("claim_outbox", { p_id: Number(body.id) });
    if (error) return json({ error: error.message }, 500);
    const row = (data ?? [])[0];
    return json(row ? { claimed: true, row: { id: row.id, handle: row.handle, body: row.body, service: row.service } } : { claimed: false });
  }
  if (body.action === "finish") {
    const { error } = await db.from("outbox")
      .update({ status: body.ok ? "sent" : "failed", error: body.ok ? null : String(body.error ?? "").slice(0, 300), finished_at: new Date().toISOString() })
      .eq("id", Number(body.id)).eq("status", "claimed");
    return error ? json({ error: error.message }, 500) : json({ ok: true });
  }
  return json({ error: "unknown action" }, 400);
});

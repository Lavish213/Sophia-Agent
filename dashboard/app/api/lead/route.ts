import { NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
const INTAKE_SECRET = process.env.INTAKE_WEBHOOK_SECRET ?? "";

export async function POST(request: Request) {
  if (!INTAKE_SECRET) {
    return NextResponse.json({ error: "intake_not_configured" }, { status: 503 });
  }

  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }

  if (body.company) {
    return NextResponse.json({ ok: true });
  }

  if (!body.phone && !body.email) {
    return NextResponse.json({ error: "phone_or_email_required" }, { status: 422 });
  }

  try {
    const upstream = await fetch(`${API_URL}/api/intake/web-form`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Intake-Secret": INTAKE_SECRET,
      },
      body: JSON.stringify({
        name: body.name,
        phone: body.phone,
        email: body.email,
        address: body.address,
        city: body.city,
        timeline: body.timeline,
        condition: body.condition,
        asking_price: body.asking_price,
        message: body.message,
      }),
    });

    if (!upstream.ok) {
      return NextResponse.json({ error: "intake_failed" }, { status: 502 });
    }

    return NextResponse.json({ ok: true });
  } catch {
    return NextResponse.json({ error: "intake_unreachable" }, { status: 502 });
  }
}

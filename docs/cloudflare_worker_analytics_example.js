export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }
    let payload;
    try {
      payload = await request.json();
    } catch {
      return new Response("Bad JSON", { status: 400 });
    }

    const key = `events:${new Date().toISOString().slice(0, 10)}`;
    const current = Number((await env.ANALYTICS_KV.get(key)) || "0");
    await env.ANALYTICS_KV.put(key, String(current + 1));
    await env.ANALYTICS_KV.put(`event:last`, JSON.stringify(payload), { expirationTtl: 60 * 60 * 24 });
    return new Response("ok");
  }
};

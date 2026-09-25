import http from "node:http";

const port = Number(process.env.PORT || 8080);
const token = String(process.env.UPBIT_PROXY_TOKEN || "");
if (!token) throw new Error("UPBIT_PROXY_TOKEN is required");

http.createServer(async (request, response) => {
  try {
    if (request.method !== "GET" || !request.url) throw new Error("GET requests only");
    if (request.headers["x-upbit-proxy-token"] !== token) {
      response.writeHead(401, { "content-type": "application/json" });
      return response.end(JSON.stringify({ error: "unauthorized" }));
    }
    const incoming = new URL(request.url, "http://localhost");
    if (!["/v1/accounts", "/v1/ticker"].includes(incoming.pathname)) {
      response.writeHead(404, { "content-type": "application/json" });
      return response.end(JSON.stringify({ error: "path_not_allowed" }));
    }
    const target = new URL(`https://api.upbit.com${incoming.pathname}${incoming.search}`);
    const headers = { accept: "application/json" };
    if (incoming.pathname === "/v1/accounts" && request.headers.authorization) headers.authorization = request.headers.authorization;
    const upstream = await fetch(target, { headers });
    const body = await upstream.text();
    response.writeHead(upstream.status, { "content-type": upstream.headers.get("content-type") || "application/json", "cache-control": "no-store" });
    response.end(body);
  } catch (error) {
    response.writeHead(400, { "content-type": "application/json" });
    response.end(JSON.stringify({ error: error instanceof Error ? error.message : "proxy_error" }));
  }
}).listen(port, "0.0.0.0", () => console.log(`Upbit fixed-IP proxy listening on ${port}`));

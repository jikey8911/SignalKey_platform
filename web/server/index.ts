import "dotenv/config";
import express from "express";
import { createServer } from "http";
import net from "net";
import HttpProxy from "http-proxy";
import { createExpressMiddleware } from "@trpc/server/adapters/express";
import { appRouter } from "./routers";
import { createContext } from "./lib/context";
import { serveStatic, setupVite } from "./lib/vite";

const BACKEND_API_URL = process.env.INTERNAL_API_URL || process.env.BACKEND_API_URL || "http://localhost:8000";

function isPortAvailable(port: number): Promise<boolean> {
  return new Promise(resolve => {
    const server = net.createServer();
    server.listen(port, () => {
      server.close(() => resolve(true));
    });
    server.on("error", () => resolve(false));
  });
}

async function findAvailablePort(startPort: number = 3000): Promise<number> {
  for (let port = startPort; port < startPort + 20; port++) {
    if (await isPortAvailable(port)) {
      return port;
    }
  }
  throw new Error(`No available port found starting from ${startPort}`);
}

async function startServer() {
  const app = express();
  const server = createServer(app);

  // Manual Proxy for Backend API (market, ml, etc.)
  // IMPORTANT: Proxy must be BEFORE body parser to avoid consuming request body
  const proxy = HttpProxy.createProxyServer({
    target: "http://127.0.0.1:8000",
    changeOrigin: true,
    ws: true,
    // Preserve cookies and headers
    xfwd: true,
  } as any);

  proxy.on("error", (err: Error, req: any, res: any) => {
    console.error("Proxy error:", err);
    if (res && "writeHead" in res && !res.headersSent) {
      res.writeHead(500, { "Content-Type": "text/plain" });
      res.end("Proxy Error");
    }
  });

  // CRITICAL: Preserve Set-Cookie headers from backend
  proxy.on("proxyRes", (proxyRes: any, req: any, res: any) => {
    // Copy Set-Cookie headers from backend response to client response
    const setCookieHeaders = proxyRes.headers["set-cookie"];
    if (setCookieHeaders) {
      res.setHeader("Set-Cookie", setCookieHeaders);
    }
  });

  // Proxy /api requests BEFORE body parser
  app.use("/api", (req, res, next) => {
    // Skip tRPC routes - they need body parsing
    if (req.url.startsWith("/trpc")) {
      return next();
    }

    // Log the request for debugging
    console.log(`[Proxy] ${req.method} /api${req.url} -> ${BACKEND_API_URL}${req.url}`);

    // Proxy all other /api requests to backend
    // req.url already has /api stripped by Express
    proxy.web(req, res, {
      target: BACKEND_API_URL,
      changeOrigin: true,
    });
  });

  // Configure body parser AFTER proxy (only for non-proxied routes)
  app.use(express.json({ limit: "50mb" }));
  app.use(express.urlencoded({ limit: "50mb", extended: true }));

  // tRPC API
  app.use(
    "/api/trpc",
    createExpressMiddleware({
      router: appRouter,
      createContext,
    })
  );

  // Handle WS Upgrades for backend
  server.on("upgrade", (req, socket, head) => {
    if (req.url?.startsWith("/ws")) {
      proxy.ws(req, socket, head, { target: "ws://127.0.0.1:8000" });
    }
  });

  // development mode uses Vite, production mode uses static files
  if (process.env.NODE_ENV === "development") {
    await setupVite(app, server);
  } else {
    serveStatic(app);
  }

  const preferredPort = parseInt(process.env.PORT || "3000");
  const port = await findAvailablePort(preferredPort);

  if (port !== preferredPort) {
    console.log(`Port ${preferredPort} is busy, using port ${port} instead`);
  }

  server.listen(port, () => {
    console.log(`Server running on http://localhost:${port}/`);
  });
}

startServer().catch(console.error);

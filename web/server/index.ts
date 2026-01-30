import "dotenv/config";
import express from "express";
import { createServer } from "http";
import net from "net";
import HttpProxy from "http-proxy";
import { createExpressMiddleware } from "@trpc/server/adapters/express";
import { authRouter } from "./auth_local";
import { appRouter } from "./routers";
import { createContext } from "./lib/context";
import { serveStatic, setupVite } from "./lib/vite";

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
  // Configure body parser with larger size limit for file uploads
  app.use(express.json({ limit: "50mb" }));
  app.use(express.urlencoded({ limit: "50mb", extended: true }));
  // Local Auth routes
  app.use("/api/auth", authRouter);
  // tRPC API
  app.use(
    "/api/trpc",
    createExpressMiddleware({
      router: appRouter,
      createContext,
    })
  );

  // Manual Proxy for Backend API (market, ml, etc.)
  const proxy = HttpProxy.createProxyServer({
    target: "http://127.0.0.1:8000",
    changeOrigin: true,
    ws: true,
  });

  proxy.on("error", (err: Error, req: any, res: any) => {
    console.error("Proxy error:", err);
    if (res && "writeHead" in res && !res.headersSent) {
      res.writeHead(500, { "Content-Type": "text/plain" });
      res.end("Proxy Error");
    }
  });

  // Proxy generic /api requests (that were not caught by above auth/trpc)
  app.use("/api", (req, res) => {
    // req.url is already stripped of /api prefix by Express when mounted here
    proxy.web(req, res);
  });

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

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
        configure: (proxy) => {
          proxy.on("error", (err) => {
            if (err.code === "ECONNRESET" || err.code === "ECONNABORTED") return;
            console.error("WS Proxy error:", err);
          });
          proxy.on("proxyReqWs", (_proxyReq, _req, socket) => {
            socket.on("error", (err) => {
              if (err.code === "ECONNRESET" || err.code === "ECONNABORTED") return;
              console.error("WS Socket error:", err);
            });
          });
        },
      },
    },
  },
});


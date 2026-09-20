import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

function terminalBaseRedirect() {
  const redirect = (req, res, next) => {
    const url = req.url || "";
    const parsed = new URL(url, "http://terminal.local");
    let target = null;
    if (parsed.pathname === "/terminal") {
      target = "/terminal/";
    } else if (parsed.pathname === "/terminal/terminal" || parsed.pathname.startsWith("/terminal/terminal/")) {
      target = `/terminal${parsed.pathname.slice("/terminal/terminal".length) || "/"}`;
    }
    if (target) {
      res.statusCode = 308;
      res.setHeader("Location", `${target}${parsed.search}`);
      res.end();
      return;
    }
    next();
  };
  return {
    name: "terminal-base-redirect",
    configureServer(server) {
      server.middlewares.use(redirect);
    },
    configurePreviewServer(server) {
      server.middlewares.use(redirect);
    },
  };
}

export default defineConfig({
  base: "/terminal/",
  plugins: [terminalBaseRedirect(), react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8081",
    },
  },
});

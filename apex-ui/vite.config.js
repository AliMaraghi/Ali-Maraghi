import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build output goes to dist/, which FastAPI mounts as static files (see console_server.py notes below).
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3001,
    proxy: {
      "/v1": {
        target: "https://localhost:9443",
        secure: false,
        changeOrigin: true,
      },
    },
  },
});

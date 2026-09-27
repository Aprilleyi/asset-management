import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const devPort = Number(env.VITE_DEV_PORT ?? 5173);
  if (!Number.isInteger(devPort) || devPort < 1 || devPort > 65535) {
    throw new Error("VITE_DEV_PORT must be a valid TCP port");
  }
  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: devPort,
      strictPort: true,
    },
  };
});

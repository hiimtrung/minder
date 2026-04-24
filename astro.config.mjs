import { defineConfig } from "astro/config";
import node from "@astrojs/node";
import tailwindcss from "@tailwindcss/vite";
import { loadEnv } from "vite";

const dashboardEnvDir = new URL("./src/dashboard", import.meta.url).pathname;
const env = loadEnv(process.env.NODE_ENV ?? "development", dashboardEnvDir, "");
const apiUrl = env.PUBLIC_API_URL ?? env.API_URL ?? "";

export default defineConfig({
  srcDir: "./src/dashboard/src",
  publicDir: "./src/dashboard/public",
  outDir: "./src/dashboard/dist",
  adapter: node({ mode: "standalone" }),
  base: "/dashboard",
  server: {
    host: true,
    port: 8808,
  },
  preview: {
    host: true,
    port: 8808,
  },
  vite: {
    envDir: dashboardEnvDir,
    plugins: [tailwindcss()],
    define: {
      "import.meta.env.PUBLIC_API_URL": JSON.stringify(apiUrl),
    },
  },
});

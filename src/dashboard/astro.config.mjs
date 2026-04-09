import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
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
    plugins: [tailwindcss()],
    define: {
      "import.meta.env.PUBLIC_API_URL": JSON.stringify(
        process.env.PUBLIC_API_URL ?? process.env.API_URL ?? "",
      ),
    },
  },
});

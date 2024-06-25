import { defineConfig } from "astro/config";
import tailwind from "@astrojs/tailwind";

export default defineConfig({
  site: "https://syangster.github.io",
  base: "/NVFlare",
  integrations: [tailwind()],
});

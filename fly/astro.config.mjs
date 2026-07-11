import { defineConfig } from "astro/config";

// https://astro.build/config
import node from "@astrojs/node";

// https://astro.build/config
export default defineConfig({
  output: "server",
  adapter: node({
    mode: "standalone",
  }),
  security: {
    // Allow the send_mail POST from outside this server.
    checkOrigin: false
  },
});

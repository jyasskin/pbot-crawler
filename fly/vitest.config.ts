/// <reference types="vitest/config" />
import { getViteConfig } from "astro/config";

export default getViteConfig({
  test: {
    fileParallelism: false,
    setupFiles: "test/setup.ts",
  },
});

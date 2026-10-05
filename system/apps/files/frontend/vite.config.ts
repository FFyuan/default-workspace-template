import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";
import { configDefaults } from "vitest/config";
import path from "path";

// dufs serves the build from its `--assets` directory under a prefix of its own (`/__dufs_v<version>__/`) and fills
// `__ASSETS_PREFIX__` into index.html with it, so the page names its bundle through that placeholder and the bundle
// names its siblings relative to itself. The names are content-hashed, which is what lets dufs's year-long immutable
// cache on that prefix pick up a new build.
const DUFS_ASSETS_PREFIX = "__ASSETS_PREFIX__";

export default defineConfig({
  test: {
    exclude: [...configDefaults.exclude, "dist/**"],
  },
  plugins: [tailwindcss()],
  root: ".",
  experimental: {
    renderBuiltUrl(filename, { hostType }) {
      if (hostType === "html") return `${DUFS_ASSETS_PREFIX}${filename}`;
      return { relative: true };
    },
  },
  build: {
    // The directory the `files` program line hands dufs as `--assets`.
    outDir: path.resolve(__dirname, "../assets"),
    emptyOutDir: true,
    // dufs serves its assets directory flat: nothing in a subdirectory of it is reachable.
    assetsDir: "",
  },
});

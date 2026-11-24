import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The end-to-end tests run their own dev server next to a normal one; a separate build
  // folder keeps the two from fighting over files (see playwright.config.ts).
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  // The Docker image sets NEXT_OUTPUT=standalone for a small self-contained server. It is
  // opt-in because the standalone copy step needs symlinks, which often fail on Windows.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
};

export default nextConfig;

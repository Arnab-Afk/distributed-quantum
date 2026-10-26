import path from "node:path";

import type { NextConfig } from "next";
import bundleAnalyzer from "@next/bundle-analyzer";

const withBundleAnalyzer = bundleAnalyzer({
  enabled: process.env.ANALYZE === "true",
});

const nextConfig: NextConfig = {
  turbopack: {
    root: path.join(__dirname, ".."),
  },
  transpilePackages: ["ngl", "openchemlib"],
  experimental: {
    optimizePackageImports: ["@radix-ui/react-icons", "lucide-react", "recharts"],
  },
};

export default withBundleAnalyzer(nextConfig);

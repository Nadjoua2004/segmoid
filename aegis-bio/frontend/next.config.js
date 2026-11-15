/** @type {import('next').NextConfig} */
// Backend address: NEXT_PUBLIC_API_URL in production (e.g. the Hugging Face Space URL), localhost in dev.
const BACKEND_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["lucide-react"],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;

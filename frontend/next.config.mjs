/** @type {import('next').NextConfig} */
const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

const nextConfig = {
  async rewrites() {
    // Only proxy when pointing at a real backend (not local Next.js API routes)
    if (!apiUrl.startsWith("http")) return [];
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;

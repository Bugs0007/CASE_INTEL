/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable turbopack for faster development
  experimental: {
    turbo: {},
  },
  // Disable strict mode for development (can be enabled in prod)
  reactStrictMode: true,
};

export default nextConfig;

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const apiUrl = (
      process.env.NEXT_PUBLIC_API_URL?.trim() || 'https://upi-fraud-detection-api.vercel.app'
    ).replace(/\/$/, '');
    return [
      {
        source: '/api/:path*',
        destination: `${apiUrl}/api/:path*`,
      },
      {
        source: '/v1/:path*',
        destination: `${apiUrl}/v1/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;

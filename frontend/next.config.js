/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const apiUrl = (
      process.env.NEXT_PUBLIC_API_URL?.trim() ||
      (process.env.NODE_ENV === 'production'
        ? 'https://upi-fraud-detection-api.vercel.app'
        : 'http://127.0.0.1:8000')
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
      {
        source: '/payments/:path*',
        destination: `${apiUrl}/payments/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;

/** @type {import('next').NextConfig} */
const nextConfig = {
  devIndicators: false,
  turbopack: {
    root: process.cwd(),
  },
  experimental: {},
  rewrites: async () => {
    return [
      {
        source: '/api/:path*',
        destination: process.env.NODE_ENV === 'development'
          ? 'http://localhost:8000/api/:path*'
          : '/api/',
      },
    ]
  },
};

export default nextConfig;

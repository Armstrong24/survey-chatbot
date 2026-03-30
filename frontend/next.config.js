/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export — builds to frontend/out/
  // FastAPI then serves these files, so everything runs on localhost:8000
  output: "export",
  trailingSlash: true,
};

module.exports = nextConfig;

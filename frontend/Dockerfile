# ---- build stage ----
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

# ---- serve stage (dev / local preview only) ----
# In production, upload dist/ to S3 instead of running this container.
FROM nginx:alpine AS serve
COPY --from=builder /app/dist /usr/share/nginx/html
# SPA fallback — all routes serve index.html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

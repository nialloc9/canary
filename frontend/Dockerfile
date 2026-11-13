# ---- build stage ----
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

# ---- dev ----
# Hot-reload via volume mount; source is NOT baked in
FROM node:20-alpine AS dev
WORKDIR /app
COPY package.json ./
RUN npm install
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ---- serve stage (prod / local preview only) ----
# In production, upload dist/ to S3 instead of running this container.
FROM nginx:alpine AS serve
COPY --from=builder /app/dist /usr/share/nginx/html
# SPA fallback — all routes serve index.html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

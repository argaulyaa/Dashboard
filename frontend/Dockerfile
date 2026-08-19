# Frontend — build React (Vite) then serve static via nginx
# The nginx official image auto-renders /etc/nginx/templates/*.template with
# envsubst at startup, substituting ${BACKEND_HOST} → backend service DNS.
FROM node:18-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.24-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
# nginx needs to reach the backend service: set BACKEND_HOST at runtime (Helm)
# Default fallback so the container also works if env is unset:
ENV BACKEND_HOST=oran-dashboard-backend
EXPOSE 80

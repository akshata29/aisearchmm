FROM node:18-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci --silent
COPY . .
ENV DOCKER_BUILD=true
RUN npm run build

FROM nginx:stable-alpine
RUN apk add --no-cache bash
WORKDIR /usr/share/nginx/html
COPY --from=build /app/dist ./
# template for runtime config injection
COPY env-config.template.js ./
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 80
ENTRYPOINT ["/entrypoint.sh"]

FROM node:24.22.0-bookworm-slim@sha256:a5f4366e834695d5f363b920c104953a535d3a9864d1bdf74566a0ebe01daee5 AS build
WORKDIR /build
RUN npm install --global pnpm@11.25.0 --ignore-scripts
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM caddy:2.11.7-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f
# 높은 내부 포트를 사용하므로 파일 capability 없이 실행.
RUN setcap -r /usr/bin/caddy
COPY --from=build /build/dist /srv
COPY deploy/Caddyfile* /etc/caddy/
ENV XDG_DATA_HOME=/data XDG_CONFIG_HOME=/config
USER 10001:10001
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile.local", "--adapter", "caddyfile"]

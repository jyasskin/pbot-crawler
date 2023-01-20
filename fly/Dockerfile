# syntax=docker/dockerfile:1
FROM node:18-alpine

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@latest --activate

COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store/v3 pnpm i --frozen-lockfile --prod

COPY prisma ./prisma
RUN pnpm prisma generate

COPY . .
RUN pnpm run build

# Setting HOST is really important so the server listens to external connections.
EXPOSE 3000
ENV HOST=0.0.0.0 PORT=3000
ENTRYPOINT ["pnpm", "run", "start"]

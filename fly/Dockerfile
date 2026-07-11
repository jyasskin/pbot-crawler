# syntax=docker/dockerfile:1
FROM node:24-alpine

WORKDIR /app

RUN corepack enable

RUN apk --no-cache add sqlite

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm i --frozen-lockfile --prod

COPY prisma ./prisma
RUN pnpm prisma generate

COPY . .
RUN pnpm run build

# Setting HOST is really important so the server listens to external connections.
EXPOSE 3000
ENV HOST=0.0.0.0 PORT=3000
ENTRYPOINT ["pnpm", "run", "start:prod"]

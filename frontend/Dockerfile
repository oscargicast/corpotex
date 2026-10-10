FROM node:24-alpine

ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    NEXT_TELEMETRY_DISABLED=1

RUN corepack enable && corepack prepare pnpm@12 --activate

WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install

COPY . .

EXPOSE 3000
CMD ["pnpm", "dev"]

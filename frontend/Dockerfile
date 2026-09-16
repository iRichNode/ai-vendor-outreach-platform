# syntax=docker/dockerfile:1
# ------------------------------------------------------------------
# AI Vendor Outreach Platform - frontend image
# Next.js app router; production server via `next start`.
# NEXT_PUBLIC_API_URL is baked at build time. Default: empty = same-origin,
# i.e. the browser calls /api/... and the reverse proxy forwards /api to the
# backend - no CORS in prod. Call paths already include the /api prefix.
# ------------------------------------------------------------------
FROM node:24-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
ARG NEXT_PUBLIC_API_URL=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

# --- runtime ---
FROM node:24-alpine AS runner

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

WORKDIR /app
RUN addgroup -S app && adduser -S app -G app

COPY --from=build --chown=app:app /app/package.json /app/package-lock.json ./
COPY --from=build --chown=app:app /app/node_modules ./node_modules
COPY --from=build --chown=app:app /app/.next ./.next
COPY --from=build --chown=app:app /app/next.config.ts ./next.config.ts
COPY --from=build --chown=app:app /app/tsconfig.json ./tsconfig.json
COPY --from=build --chown=app:app /app/postcss.config.mjs ./postcss.config.mjs
COPY --from=build --chown=app:app /app/next-env.d.ts ./next-env.d.ts

USER app
EXPOSE 3000
CMD ["npm", "run", "start"]
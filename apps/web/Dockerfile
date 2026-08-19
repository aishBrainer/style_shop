# --- dev -------------------------------------------------------------------
FROM node:20-alpine AS dev
WORKDIR /srv/web
ENV NEXT_TELEMETRY_DISABLED=1
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]


# --- build -----------------------------------------------------------------
FROM node:20-alpine AS builder
WORKDIR /srv/web
ENV NEXT_TELEMETRY_DISABLED=1
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build


# --- production ------------------------------------------------------------
FROM node:20-alpine AS production
WORKDIR /srv/web
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

# `output: standalone` emits only the files the server actually needs.
COPY --from=builder /srv/web/public ./public
COPY --from=builder --chown=nextjs:nodejs /srv/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /srv/web/.next/static ./.next/static

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]

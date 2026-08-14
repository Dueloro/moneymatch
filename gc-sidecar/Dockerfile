# The Game Coordinator sidecar.
#
# A separate image from the API because it is a separate runtime: the GC speaks
# protobuf over the Steam network and has no maintained Python client, so this
# is the one piece that must be Node.
#
# Deployed as a *private* service. It can read match data for arbitrary players,
# so it must never face the internet; the shared secret is a second lock, not
# the only one.
FROM node:22-slim

WORKDIR /app

# Install deps first so a code edit does not bust the dependency layer.
COPY gc-sidecar/package.json gc-sidecar/package-lock.json ./
RUN npm ci --omit=dev

COPY gc-sidecar/ ./

ENV NODE_ENV=production
# Reachable from the API container. Private networking, plus the mandatory
# shared secret, is what keeps that safe.
ENV GC_BIND_HOST=0.0.0.0

# Supervised: the GC drops connections, and an unsupervised sidecar that exits
# takes every CS2 settlement with it until someone notices.
CMD ["node", "supervise.js"]

FROM node:20-slim

WORKDIR /app

# Lockfile included so the image installs the resolved tree, not a fresh resolution.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# NEXT_PUBLIC_* values are inlined by Next at BUILD time, not read at runtime. Setting
# this in compose's `environment:` therefore does nothing: it has to be a build arg, or
# the image ships whatever the fallback in lib/api.ts was when it was built.
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE

COPY . .
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]

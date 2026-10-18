FROM node:22-bookworm-slim AS dependencies

WORKDIR /app

COPY package*.json ./
RUN npm ci --omit=dev --ignore-scripts

FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci --ignore-scripts
COPY tsconfig.ai.json ./
COPY src/ai ./src/ai
RUN npm run build

FROM node:22-bookworm-slim AS runtime

ENV NODE_ENV=production
WORKDIR /app

# Baseline needs only Node. Optional CPU inference, built explicitly by the operator.
ARG INSTALL_TRAIL_ML=false
COPY ml/requirements.lock.txt ./ml/requirements.lock.txt
RUN if [ "$INSTALL_TRAIL_ML" = "true" ]; then \
      apt-get update && apt-get install -y --no-install-recommends python3 python3-venv && \
      python3 -m venv /opt/trail-ml && \
      /opt/trail-ml/bin/pip install --no-cache-dir -r ml/requirements.lock.txt && \
      rm -rf /var/lib/apt/lists/*; \
    fi
ENV PATH="/opt/trail-ml/bin:${PATH}"

COPY --from=dependencies /app/node_modules ./node_modules
COPY package*.json ./
COPY migrations ./migrations
COPY src ./src
COPY ml ./ml
COPY --from=build /app/dist ./dist

USER node

EXPOSE 3001

CMD ["npm", "start"]

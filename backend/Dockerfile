FROM node:22-bookworm-slim AS dependencies

WORKDIR /app

COPY package*.json ./
<<<<<<< HEAD
RUN npm ci --omit=dev --ignore-scripts
=======
RUN npm ci --omit=dev
>>>>>>> 9c37b5b78195f678040f02b776d8b3b6eecb0110

FROM node:22-bookworm-slim AS runtime

ENV NODE_ENV=production
WORKDIR /app

COPY --from=dependencies /app/node_modules ./node_modules
COPY package*.json ./
<<<<<<< HEAD
=======
COPY migrations ./migrations
>>>>>>> 9c37b5b78195f678040f02b776d8b3b6eecb0110
COPY src ./src

USER node

EXPOSE 3001

CMD ["npm", "start"]

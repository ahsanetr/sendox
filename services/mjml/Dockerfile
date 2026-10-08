FROM node:22-alpine

ENV NODE_ENV=production
WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund

COPY server.js render.js ./

EXPOSE 7070
CMD ["node", "server.js"]

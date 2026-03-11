# docker/frontend.dev.Dockerfile
FROM node:20.20.0-bookworm-slim

WORKDIR /workspace/frontend

RUN npm install -g npm@11.10.1

COPY frontend/package.json frontend/package-lock.json ./

RUN npm ci

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5174"]

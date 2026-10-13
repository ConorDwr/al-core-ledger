FROM node:20-slim

WORKDIR /app

# Install dependencies first so Docker can cache this layer
COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE 8545

# --hostname 0.0.0.0 makes the node reachable from outside the container
CMD ["npx", "hardhat", "node", "--hostname", "0.0.0.0"]

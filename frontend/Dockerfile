FROM node:18-alpine

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm install --legacy-peer-deps

# Copy source
COPY . .

# Expose port
EXPOSE 3000

# Run development server - use PORT env var for cloud platforms like Render
CMD npm run dev -- --host 0.0.0.0 --port ${PORT:-3000}


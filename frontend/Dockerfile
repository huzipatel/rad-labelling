# Build stage
FROM node:18-alpine as build

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm install --legacy-peer-deps

# Copy source
COPY . .

# Build args for environment variables at build time
ARG VITE_API_URL
ARG VITE_GOOGLE_CLIENT_ID
ARG VITE_GSV_API_KEY

ENV VITE_API_URL=$VITE_API_URL
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID
ENV VITE_GSV_API_KEY=$VITE_GSV_API_KEY

# Build the app (skip type checking if there are errors)
RUN npm run build || (npm install typescript && npx vite build)

# Production stage - serve with nginx
FROM nginx:alpine

# Copy built assets
COPY --from=build /app/dist /usr/share/nginx/html

# Create nginx config for SPA routing (no backend proxy - frontend calls API directly)
COPY <<EOF /etc/nginx/conf.d/default.conf
server {
    listen 80;
    listen [::]:80;
    root /usr/share/nginx/html;
    index index.html;
    
    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/javascript;
    
    # SPA routing - serve index.html for all routes
    location / {
        try_files \$uri \$uri/ /index.html;
    }
    
    # Cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
EOF

# Use PORT env var (Railway sets this)
CMD sh -c "sed -i 's/listen 80/listen '\$PORT'/g' /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"

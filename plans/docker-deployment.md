# Docker Deployment Guide - The Goodies Platform

## Overview

This guide provides comprehensive instructions for containerizing and deploying The Goodies platform using Docker and container orchestration platforms.

## Docker Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Host / Kubernetes Node            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  FunkyGibbon │  │  PostgreSQL  │  │    Redis     │     │
│  │   Container  │  │  Container   │  │  Container   │     │
│  │   Port:8080  │  │  Port:5432   │  │  Port:6379   │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│         │                  │                  │              │
│         └──────────────────┴──────────────────┘             │
│                            │                                 │
│                     Docker Network                           │
│                   (funkygibbon-net)                         │
└─────────────────────────────────────────────────────────────┘
```

## Dockerfile Configurations

### Production Dockerfile - FunkyGibbon API

```dockerfile
# Build stage
FROM golang:1.21-alpine AS builder

# Install build dependencies
RUN apk add --no-cache git make gcc musl-dev

# Set working directory
WORKDIR /build

# Copy go mod files
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY . .

# Build the application
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -ldflags="-w -s" -o funkygibbon cmd/api/main.go

# Runtime stage
FROM alpine:3.19

# Install runtime dependencies
RUN apk add --no-cache ca-certificates tzdata

# Create non-root user
RUN addgroup -g 1001 -S funkygibbon && \
    adduser -u 1001 -S funkygibbon -G funkygibbon

# Set working directory
WORKDIR /app

# Copy binary from builder
COPY --from=builder /build/funkygibbon .
COPY --from=builder /build/config ./config
COPY --from=builder /build/migrations ./migrations

# Change ownership
RUN chown -R funkygibbon:funkygibbon /app

# Use non-root user
USER funkygibbon

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8080/health || exit 1

# Run the application
ENTRYPOINT ["./funkygibbon"]
CMD ["serve"]
```

### Development Dockerfile

```dockerfile
# Development Dockerfile with hot reload
FROM golang:1.21-alpine

# Install development tools
RUN apk add --no-cache git make gcc musl-dev postgresql-client redis

# Install air for hot reload
RUN go install github.com/cosmtrek/air@latest

# Install development tools
RUN go install github.com/golang/mock/mockgen@latest && \
    go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest && \
    go install github.com/swaggo/swag/cmd/swag@latest

# Set working directory
WORKDIR /app

# Copy go mod files
COPY go.mod go.sum ./
RUN go mod download

# Copy air config
COPY .air.toml .

# Expose ports
EXPOSE 8080 2345

# Run with air for hot reload
CMD ["air", "-c", ".air.toml"]
```

### Multi-Architecture Build

```dockerfile
# Multi-arch Dockerfile
FROM --platform=$BUILDPLATFORM golang:1.21-alpine AS builder

ARG TARGETOS
ARG TARGETARCH

# Install dependencies
RUN apk add --no-cache git make gcc musl-dev

WORKDIR /build

# Copy and download dependencies
COPY go.mod go.sum ./
RUN go mod download

# Copy source
COPY . .

# Build for target platform
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
    go build -ldflags="-w -s" -o funkygibbon cmd/api/main.go

# Runtime stage
FROM alpine:3.19

RUN apk add --no-cache ca-certificates tzdata

WORKDIR /app

COPY --from=builder /build/funkygibbon .

EXPOSE 8080

ENTRYPOINT ["./funkygibbon"]
```

## Docker Compose Configurations

### Production Docker Compose

```yaml
version: '3.8'

services:
  api:
    image: funkygibbon:latest
    container_name: funkygibbon-api
    restart: unless-stopped
    environment:
      - APP_ENV=production
      - DB_HOST=postgres
      - DB_PORT=5432
      - DB_NAME=funkygibbon
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=${REDIS_PASSWORD}
      - JWT_SECRET=${JWT_SECRET}
    ports:
      - "8080:8080"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - funkygibbon-net
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 512M
        reservations:
          cpus: '0.5'
          memory: 256M

  postgres:
    image: postgres:16-alpine
    container_name: funkygibbon-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_DB=funkygibbon
      - POSTGRES_USER=${DB_USER}
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_INITDB_ARGS=--encoding=UTF-8 --lc-collate=C --lc-ctype=C
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/init-db.sql:/docker-entrypoint-initdb.d/init.sql:ro
    networks:
      - funkygibbon-net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d funkygibbon"]
      interval: 10s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 1G

  redis:
    image: redis:7-alpine
    container_name: funkygibbon-redis
    restart: unless-stopped
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD}
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru
      --appendonly yes
      --appendfsync everysec
    volumes:
      - redis_data:/data
    networks:
      - funkygibbon-net
    healthcheck:
      test: ["CMD", "redis-cli", "--pass", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 256M

  nginx:
    image: nginx:alpine
    container_name: funkygibbon-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - nginx_cache:/var/cache/nginx
    depends_on:
      - api
    networks:
      - funkygibbon-net
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local
  nginx_cache:
    driver: local

networks:
  funkygibbon-net:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

### Development Docker Compose

```yaml
version: '3.8'

services:
  api:
    build:
      context: .
      dockerfile: Dockerfile.dev
    container_name: funkygibbon-api-dev
    environment:
      - APP_ENV=development
      - DB_HOST=postgres
      - REDIS_HOST=redis
      - DB_PASSWORD=dev_password
      - REDIS_PASSWORD=dev_password
      - JWT_SECRET=dev_secret_key
    ports:
      - "8080:8080"
      - "2345:2345"  # Debugger port
    volumes:
      - ./:/app
      - /app/vendor  # Exclude vendor directory
    depends_on:
      - postgres
      - redis
    networks:
      - funkygibbon-dev

  postgres:
    image: postgres:16-alpine
    container_name: funkygibbon-postgres-dev
    environment:
      - POSTGRES_DB=funkygibbon
      - POSTGRES_USER=funkygibbon_user
      - POSTGRES_PASSWORD=dev_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data_dev:/var/lib/postgresql/data
    networks:
      - funkygibbon-dev

  redis:
    image: redis:7-alpine
    container_name: funkygibbon-redis-dev
    command: redis-server --requirepass dev_password
    ports:
      - "6379:6379"
    volumes:
      - redis_data_dev:/data
    networks:
      - funkygibbon-dev

  pgadmin:
    image: dpage/pgadmin4:latest
    container_name: funkygibbon-pgadmin
    environment:
      - PGADMIN_DEFAULT_EMAIL=admin@local.dev
      - PGADMIN_DEFAULT_PASSWORD=admin
    ports:
      - "5050:80"
    networks:
      - funkygibbon-dev

  redis-commander:
    image: rediscommander/redis-commander:latest
    container_name: funkygibbon-redis-commander
    environment:
      - REDIS_HOSTS=local:redis:6379:0:dev_password
    ports:
      - "8081:8081"
    networks:
      - funkygibbon-dev

volumes:
  postgres_data_dev:
  redis_data_dev:

networks:
  funkygibbon-dev:
    driver: bridge
```

## Building and Running

### Local Development

```bash
# Start development environment
docker-compose -f docker-compose.dev.yml up -d

# View logs
docker-compose -f docker-compose.dev.yml logs -f api

# Run database migrations
docker-compose -f docker-compose.dev.yml exec api go run cmd/migrate/main.go up

# Access the application
curl http://localhost:8080/health

# Stop the environment
docker-compose -f docker-compose.dev.yml down
```

### Production Build

```bash
# Build production image
docker build -t funkygibbon:latest -f Dockerfile .

# Tag for registry
docker tag funkygibbon:latest registry.example.com/funkygibbon:latest

# Push to registry
docker push registry.example.com/funkygibbon:latest

# Run production stack
docker-compose up -d

# Scale the API service
docker-compose up -d --scale api=3
```

### Multi-Architecture Build

```bash
# Setup buildx
docker buildx create --name multiarch --use

# Build for multiple platforms
docker buildx build \
  --platform linux/amd64,linux/arm64,linux/arm/v7 \
  --tag registry.example.com/funkygibbon:latest \
  --push \
  .
```

## Container Registry Setup

### Docker Hub

```bash
# Login to Docker Hub
docker login

# Build and push
docker build -t username/funkygibbon:latest .
docker push username/funkygibbon:latest
```

### AWS ECR

```bash
# Get login token
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  123456789.dkr.ecr.us-east-1.amazonaws.com

# Create repository
aws ecr create-repository --repository-name funkygibbon

# Build and push
docker build -t funkygibbon .
docker tag funkygibbon:latest \
  123456789.dkr.ecr.us-east-1.amazonaws.com/funkygibbon:latest
docker push \
  123456789.dkr.ecr.us-east-1.amazonaws.com/funkygibbon:latest
```

### Google Container Registry

```bash
# Configure Docker for GCR
gcloud auth configure-docker

# Build and push
docker build -t gcr.io/project-id/funkygibbon:latest .
docker push gcr.io/project-id/funkygibbon:latest
```

## Kubernetes Deployment

### Deployment Manifest

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: funkygibbon-api
  namespace: production
  labels:
    app: funkygibbon
    component: api
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: funkygibbon
      component: api
  template:
    metadata:
      labels:
        app: funkygibbon
        component: api
    spec:
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchExpressions:
                - key: app
                  operator: In
                  values:
                  - funkygibbon
              topologyKey: kubernetes.io/hostname
      containers:
      - name: api
        image: registry.example.com/funkygibbon:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 8080
          name: http
          protocol: TCP
        env:
        - name: APP_ENV
          value: "production"
        - name: DB_HOST
          value: "postgres-service"
        - name: REDIS_HOST
          value: "redis-service"
        envFrom:
        - secretRef:
            name: funkygibbon-secrets
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3
        volumeMounts:
        - name: config
          mountPath: /app/config
          readOnly: true
      volumes:
      - name: config
        configMap:
          name: funkygibbon-config
```

### Service Manifest

```yaml
apiVersion: v1
kind: Service
metadata:
  name: funkygibbon-api-service
  namespace: production
  labels:
    app: funkygibbon
    component: api
spec:
  type: ClusterIP
  selector:
    app: funkygibbon
    component: api
  ports:
  - port: 80
    targetPort: 8080
    protocol: TCP
    name: http
```

### Horizontal Pod Autoscaler

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: funkygibbon-api-hpa
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: funkygibbon-api
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

## Docker Swarm Deployment

### Initialize Swarm

```bash
# Initialize swarm on manager node
docker swarm init --advertise-addr 10.0.0.1

# Join worker nodes
docker swarm join --token SWMTKN-1-xxx 10.0.0.1:2377
```

### Stack Configuration

```yaml
version: '3.8'

services:
  api:
    image: registry.example.com/funkygibbon:latest
    deploy:
      replicas: 3
      update_config:
        parallelism: 1
        delay: 10s
        failure_action: rollback
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
      placement:
        constraints:
          - node.role == worker
    environment:
      - APP_ENV=production
    secrets:
      - db_password
      - jwt_secret
    networks:
      - funkygibbon-net
    ports:
      - "8080:8080"

  postgres:
    image: postgres:16-alpine
    deploy:
      replicas: 1
      placement:
        constraints:
          - node.labels.db == true
    environment:
      - POSTGRES_PASSWORD_FILE=/run/secrets/db_password
    secrets:
      - db_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - funkygibbon-net

secrets:
  db_password:
    external: true
  jwt_secret:
    external: true

networks:
  funkygibbon-net:
    driver: overlay
    attachable: true

volumes:
  postgres_data:
    driver: local
```

### Deploy Stack

```bash
# Create secrets
echo "secure_password" | docker secret create db_password -
echo "jwt_secret_key" | docker secret create jwt_secret -

# Deploy stack
docker stack deploy -c docker-stack.yml funkygibbon

# Check services
docker stack services funkygibbon

# Scale service
docker service scale funkygibbon_api=5
```

## Security Best Practices

### Image Security

```dockerfile
# Use specific versions, not latest
FROM golang:1.21.5-alpine3.19

# Run security scan
RUN apk add --no-cache curl && \
    curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin

# Scan image during build
RUN trivy filesystem --exit-code 1 --no-progress /

# Use non-root user
USER 1001:1001
```

### Runtime Security

```yaml
# Docker Compose security options
services:
  api:
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    read_only: true
    tmpfs:
      - /tmp
```

### Secret Management

```bash
# Use Docker secrets
docker secret create db_password ./secrets/db_password.txt

# Use BuildKit secrets for build time
docker build --secret id=npm,src=$HOME/.npmrc .

# In Dockerfile
RUN --mount=type=secret,id=npm,target=/root/.npmrc \
    npm install --production
```

## Monitoring and Logging

### Prometheus Metrics

```yaml
# Add Prometheus service
prometheus:
  image: prom/prometheus:latest
  volumes:
    - ./prometheus.yml:/etc/prometheus/prometheus.yml
    - prometheus_data:/prometheus
  command:
    - '--config.file=/etc/prometheus/prometheus.yml'
    - '--storage.tsdb.path=/prometheus'
  ports:
    - "9090:9090"
```

### ELK Stack

```yaml
# Elasticsearch
elasticsearch:
  image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
  environment:
    - discovery.type=single-node
    - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
  volumes:
    - elasticsearch_data:/usr/share/elasticsearch/data

# Logstash
logstash:
  image: docker.elastic.co/logstash/logstash:8.11.0
  volumes:
    - ./logstash.conf:/usr/share/logstash/pipeline/logstash.conf
  depends_on:
    - elasticsearch

# Kibana
kibana:
  image: docker.elastic.co/kibana/kibana:8.11.0
  environment:
    - ELASTICSEARCH_HOSTS=http://elasticsearch:9200
  ports:
    - "5601:5601"
  depends_on:
    - elasticsearch
```

## Troubleshooting

### Common Issues

```bash
# Container won't start
docker logs funkygibbon-api

# Network connectivity issues
docker exec funkygibbon-api ping postgres

# Resource constraints
docker stats

# Inspect container
docker inspect funkygibbon-api

# Execute commands in container
docker exec -it funkygibbon-api sh

# Check Docker daemon logs
journalctl -u docker.service
```

### Performance Optimization

```bash
# Limit container resources
docker run -m 512m --cpus="1.0" funkygibbon:latest

# Use tmpfs for temporary files
docker run --tmpfs /tmp:rw,noexec,nosuid,size=100m funkygibbon:latest

# Enable BuildKit for faster builds
DOCKER_BUILDKIT=1 docker build .

# Prune unused resources
docker system prune -a
```

## CI/CD Integration

### GitHub Actions

```yaml
name: Docker Build and Push

on:
  push:
    branches: [main]
    tags: ['v*']

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up QEMU
      uses: docker/setup-qemu-action@v2
      
    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v2
      
    - name: Login to Registry
      uses: docker/login-action@v2
      with:
        registry: registry.example.com
        username: ${{ secrets.REGISTRY_USERNAME }}
        password: ${{ secrets.REGISTRY_PASSWORD }}
        
    - name: Build and push
      uses: docker/build-push-action@v4
      with:
        context: .
        platforms: linux/amd64,linux/arm64
        push: true
        tags: |
          registry.example.com/funkygibbon:latest
          registry.example.com/funkygibbon:${{ github.sha }}
        cache-from: type=gha
        cache-to: type=gha,mode=max
```
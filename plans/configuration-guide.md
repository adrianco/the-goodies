# Configuration Guide - The Goodies Platform

## Overview

This guide covers all configuration options for The Goodies platform components, including environment variables, configuration files, and runtime parameters.

## FunkyGibbon API Configuration

### Environment Variables

#### Core Configuration
```bash
# Application
APP_NAME=funkygibbon
APP_ENV=development|staging|production
APP_PORT=8080
APP_HOST=0.0.0.0
APP_VERSION=1.0.0

# Logging
LOG_LEVEL=debug|info|warn|error
LOG_FORMAT=json|text
LOG_OUTPUT=stdout|file
LOG_FILE_PATH=/var/log/funkygibbon/app.log
LOG_MAX_SIZE=100M
LOG_MAX_AGE=30d
LOG_MAX_BACKUPS=10

# API Configuration
API_PREFIX=/api/v1
API_TIMEOUT=30s
API_MAX_REQUEST_SIZE=10MB
API_RATE_LIMIT=100
API_RATE_WINDOW=1m
```

#### Database Configuration
```bash
# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=funkygibbon
DB_USER=funkygibbon_user
DB_PASSWORD=<secure-password>
DB_SSL_MODE=require|disable
DB_MAX_CONNECTIONS=100
DB_MAX_IDLE_CONNECTIONS=10
DB_CONNECTION_TIMEOUT=30s
DB_CONNECTION_MAX_LIFETIME=1h

# Connection Pool
DB_POOL_MIN_SIZE=5
DB_POOL_MAX_SIZE=20
DB_POOL_ACQUIRE_TIMEOUT=30s
DB_POOL_IDLE_TIMEOUT=10m
```

#### Cache Configuration
```bash
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=<secure-password>
REDIS_DB=0
REDIS_MAX_RETRIES=3
REDIS_POOL_SIZE=10
REDIS_POOL_TIMEOUT=30s
REDIS_READ_TIMEOUT=3s
REDIS_WRITE_TIMEOUT=3s

# Cache Settings
CACHE_TTL=1h
CACHE_PREFIX=funkygibbon:
CACHE_COMPRESSION=true
```

#### Authentication & Security
```bash
# JWT Configuration
JWT_SECRET=<secure-secret>
JWT_ACCESS_TOKEN_EXPIRY=15m
JWT_REFRESH_TOKEN_EXPIRY=7d
JWT_ISSUER=funkygibbon
JWT_AUDIENCE=funkygibbon-api

# OAuth Providers
OAUTH_GITHUB_CLIENT_ID=<client-id>
OAUTH_GITHUB_CLIENT_SECRET=<client-secret>
OAUTH_GITHUB_REDIRECT_URL=http://localhost:8080/auth/github/callback

OAUTH_GOOGLE_CLIENT_ID=<client-id>
OAUTH_GOOGLE_CLIENT_SECRET=<client-secret>
OAUTH_GOOGLE_REDIRECT_URL=http://localhost:8080/auth/google/callback

# Security
CORS_ALLOWED_ORIGINS=http://localhost:3000,https://app.example.com
CORS_ALLOWED_METHODS=GET,POST,PUT,DELETE,OPTIONS
CORS_ALLOWED_HEADERS=Content-Type,Authorization
CORS_MAX_AGE=86400

CSRF_ENABLED=true
CSRF_TOKEN_LENGTH=32
CSRF_COOKIE_NAME=_csrf
CSRF_HEADER_NAME=X-CSRF-Token

# Encryption
ENCRYPTION_KEY=<32-byte-key>
ENCRYPTION_ALGORITHM=AES-256-GCM
```

#### External Services
```bash
# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<access-key>
AWS_SECRET_ACCESS_KEY=<secret-key>
AWS_S3_BUCKET=funkygibbon-assets
AWS_S3_ENDPOINT=https://s3.amazonaws.com

# Email Service
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=<sendgrid-api-key>
SMTP_FROM=noreply@funkygibbon.com
SMTP_FROM_NAME=FunkyGibbon

# Monitoring
SENTRY_DSN=https://<key>@sentry.io/<project>
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1

# Feature Flags
FEATURE_NEW_UI=true
FEATURE_BETA_API=false
FEATURE_ANALYTICS=true
```

### Configuration Files

#### config.yaml
```yaml
server:
  name: funkygibbon
  version: 1.0.0
  environment: production
  
  http:
    port: 8080
    host: 0.0.0.0
    read_timeout: 30s
    write_timeout: 30s
    idle_timeout: 120s
    max_header_bytes: 1048576
    
  grpc:
    port: 9090
    max_recv_msg_size: 4194304
    max_send_msg_size: 4194304

middleware:
  - recovery
  - logger
  - cors
  - compression
  - rate_limit
  - auth

features:
  api_v2: false
  webhooks: true
  batch_processing: true
  real_time_updates: true

limits:
  max_upload_size: 100MB
  max_batch_size: 1000
  max_concurrent_jobs: 10
  rate_limit_requests: 100
  rate_limit_window: 1m
```

#### database.yaml
```yaml
primary:
  driver: postgres
  host: ${DB_HOST}
  port: ${DB_PORT}
  database: ${DB_NAME}
  username: ${DB_USER}
  password: ${DB_PASSWORD}
  
  pool:
    max_open: 25
    max_idle: 5
    max_lifetime: 1h
    
  options:
    sslmode: require
    timezone: UTC
    
read_replicas:
  - host: read-replica-1.example.com
    weight: 50
  - host: read-replica-2.example.com
    weight: 50
    
migrations:
  auto_migrate: false
  migrations_path: ./migrations
```

## WildThing SDK Configuration

### Swift Package Configuration

#### Package.swift
```swift
// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "WildThing",
    platforms: [
        .iOS(.v14),
        .macOS(.v11),
        .tvOS(.v14),
        .watchOS(.v7)
    ],
    products: [
        .library(
            name: "WildThing",
            targets: ["WildThing"]
        ),
    ],
    dependencies: [
        .package(url: "https://github.com/apple/swift-nio.git", from: "2.65.0"),
        .package(url: "https://github.com/swift-server/async-http-client.git", from: "1.19.0")
    ],
    targets: [
        .target(
            name: "WildThing",
            dependencies: [
                .product(name: "NIO", package: "swift-nio"),
                .product(name: "AsyncHTTPClient", package: "async-http-client")
            ],
            resources: [
                .process("Resources")
            ]
        ),
        .testTarget(
            name: "WildThingTests",
            dependencies: ["WildThing"]
        ),
    ]
)
```

### SDK Initialization

#### Basic Configuration
```swift
import WildThing

let config = WildThingConfiguration(
    apiKey: "your-api-key",
    baseURL: "https://api.funkygibbon.com",
    environment: .production
)

let client = WildThingClient(configuration: config)
```

#### Advanced Configuration
```swift
let config = WildThingConfiguration(
    apiKey: "your-api-key",
    baseURL: "https://api.funkygibbon.com",
    environment: .production,
    timeout: 30,
    retryPolicy: .exponential(maxRetries: 3),
    cachePolicy: .aggressive,
    logLevel: .info
)

// Custom headers
config.additionalHeaders = [
    "X-Client-Version": "1.0.0",
    "X-Platform": "iOS"
]

// Proxy configuration
config.proxyConfiguration = ProxyConfiguration(
    host: "proxy.example.com",
    port: 8888,
    username: "user",
    password: "pass"
)

// Certificate pinning
config.certificatePins = [
    "sha256/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
]
```

## Docker Configuration

### Docker Compose - Development
```yaml
version: '3.8'

services:
  api:
    build:
      context: .
      dockerfile: Dockerfile.dev
    environment:
      - APP_ENV=development
      - DB_HOST=postgres
      - REDIS_HOST=redis
    ports:
      - "8080:8080"
    volumes:
      - ./src:/app/src
      - ./config:/app/config
    depends_on:
      - postgres
      - redis
    networks:
      - funkygibbon-net

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: funkygibbon
      POSTGRES_USER: funkygibbon_user
      POSTGRES_PASSWORD: dev_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    networks:
      - funkygibbon-net

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    networks:
      - funkygibbon-net

  pgadmin:
    image: dpage/pgadmin4
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@funkygibbon.local
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5050:80"
    networks:
      - funkygibbon-net

volumes:
  postgres_data:
  redis_data:

networks:
  funkygibbon-net:
    driver: bridge
```

### Kubernetes Configuration

#### ConfigMap
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: funkygibbon-config
  namespace: production
data:
  APP_ENV: "production"
  APP_PORT: "8080"
  LOG_LEVEL: "info"
  API_PREFIX: "/api/v1"
  CACHE_TTL: "3600"
```

#### Secret
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: funkygibbon-secrets
  namespace: production
type: Opaque
stringData:
  DB_PASSWORD: "secure-password"
  REDIS_PASSWORD: "redis-password"
  JWT_SECRET: "jwt-secret-key"
  AWS_SECRET_ACCESS_KEY: "aws-secret"
```

#### Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: funkygibbon
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: funkygibbon
  template:
    metadata:
      labels:
        app: funkygibbon
    spec:
      containers:
      - name: api
        image: funkygibbon:latest
        ports:
        - containerPort: 8080
        envFrom:
        - configMapRef:
            name: funkygibbon-config
        - secretRef:
            name: funkygibbon-secrets
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
```

## Environment-Specific Configurations

### Development
```bash
# Relaxed security for local development
CORS_ALLOWED_ORIGINS=*
JWT_ACCESS_TOKEN_EXPIRY=1d
LOG_LEVEL=debug
DB_SSL_MODE=disable
FEATURE_DEBUG_ENDPOINTS=true
```

### Staging
```bash
# Production-like but with debugging
CORS_ALLOWED_ORIGINS=https://staging.funkygibbon.com
JWT_ACCESS_TOKEN_EXPIRY=30m
LOG_LEVEL=info
DB_SSL_MODE=require
FEATURE_DEBUG_ENDPOINTS=true
```

### Production
```bash
# Strict security and performance
CORS_ALLOWED_ORIGINS=https://app.funkygibbon.com
JWT_ACCESS_TOKEN_EXPIRY=15m
LOG_LEVEL=warn
DB_SSL_MODE=require
FEATURE_DEBUG_ENDPOINTS=false
```

## Configuration Best Practices

### Security
1. Never commit secrets to version control
2. Use environment variables for sensitive data
3. Rotate secrets regularly
4. Use least privilege principle
5. Enable audit logging

### Performance
1. Tune connection pools based on load
2. Set appropriate timeouts
3. Enable caching where possible
4. Use connection multiplexing
5. Monitor resource usage

### Maintenance
1. Document all configuration changes
2. Use configuration validation
3. Implement health checks
4. Set up proper logging
5. Monitor configuration drift

## Troubleshooting

### Common Issues

#### Database Connection Errors
```bash
# Check connection string
echo $DB_HOST $DB_PORT $DB_NAME

# Test connection
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME

# Verify SSL settings
openssl s_client -connect $DB_HOST:$DB_PORT
```

#### Redis Connection Issues
```bash
# Test Redis connection
redis-cli -h $REDIS_HOST -p $REDIS_PORT ping

# Check authentication
redis-cli -h $REDIS_HOST -p $REDIS_PORT -a $REDIS_PASSWORD ping
```

#### Configuration Loading
```bash
# Validate configuration file
funkygibbon validate-config --file config.yaml

# Check environment variables
funkygibbon env-check

# Debug configuration loading
LOG_LEVEL=debug funkygibbon start
```

## Configuration Management Tools

### HashiCorp Consul
```hcl
service {
  name = "funkygibbon"
  tags = ["api", "v1"]
  port = 8080
  
  check {
    http     = "http://localhost:8080/health"
    interval = "10s"
  }
}

key_prefix "funkygibbon/config/" {
  path = "config/"
  
  handler = "write" {
    command = "/usr/local/bin/reload-config.sh"
  }
}
```

### AWS Parameter Store
```bash
# Store configuration
aws ssm put-parameter \
  --name "/funkygibbon/production/db_password" \
  --value "secure-password" \
  --type SecureString

# Retrieve configuration
aws ssm get-parameter \
  --name "/funkygibbon/production/db_password" \
  --with-decryption
```

### Kubernetes ConfigMaps
```bash
# Create from file
kubectl create configmap funkygibbon-config \
  --from-file=config.yaml

# Create from literals
kubectl create configmap funkygibbon-config \
  --from-literal=app_env=production \
  --from-literal=log_level=info

# Update configuration
kubectl edit configmap funkygibbon-config
```
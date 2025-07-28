# Security and Authentication Architecture

## Overview

This document outlines the comprehensive security architecture for The Goodies ecosystem, covering authentication, authorization, encryption, and security best practices for both WildThing (client) and FunkyGibbon (server) components.

## Security Principles

1. **Defense in Depth**: Multiple layers of security controls
2. **Zero Trust**: Verify everything, trust nothing
3. **Least Privilege**: Minimal permissions required
4. **Privacy by Design**: Data protection built-in
5. **Fail Secure**: Safe defaults on failure

## Authentication Architecture

### 1. Device Authentication (WildThing)

```swift
// Device Certificate Generation
class DeviceAuthenticator {
    private let keychain = KeychainManager()
    private let deviceId = UUID()
    
    func generateDeviceIdentity() throws -> DeviceIdentity {
        // Generate device keypair
        let privateKey = try Curve25519.KeyGeneration.generatePrivateKey()
        let publicKey = privateKey.publicKey
        
        // Create device certificate request
        let certificateRequest = DeviceCertificateRequest(
            deviceId: deviceId.uuidString,
            publicKey: publicKey.rawRepresentation,
            deviceInfo: DeviceInfo(
                platform: "iOS",
                version: UIDevice.current.systemVersion,
                model: UIDevice.current.model
            )
        )
        
        // Store in secure keychain
        try keychain.store(
            privateKey: privateKey,
            identifier: "com.wildthing.device.private"
        )
        
        return DeviceIdentity(
            deviceId: deviceId.uuidString,
            certificate: certificateRequest
        )
    }
    
    func authenticateDevice() async throws -> AuthToken {
        let identity = try loadDeviceIdentity()
        let challenge = try await requestChallenge(identity.deviceId)
        
        // Sign challenge with device private key
        let signature = try signChallenge(challenge, with: identity.privateKey)
        
        // Exchange for auth token
        let response = try await submitChallenge(
            deviceId: identity.deviceId,
            challenge: challenge,
            signature: signature
        )
        
        // Store tokens securely
        try keychain.store(
            accessToken: response.accessToken,
            refreshToken: response.refreshToken
        )
        
        return response
    }
}
```

### 2. User Authentication

```python
# funkygibbon/auth/user_auth.py
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class UserAuthService:
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire = timedelta(minutes=15)
        self.refresh_token_expire = timedelta(days=30)
    
    async def authenticate_user(
        self,
        username: str,
        password: str,
        device_id: str
    ) -> AuthResponse:
        # Verify user credentials
        user = await self.get_user(username)
        if not user or not self.verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid credentials")
        
        # Check device authorization
        if not await self.is_device_authorized(user.id, device_id):
            # New device - require additional verification
            await self.send_device_verification(user, device_id)
            raise DeviceNotAuthorized("Device verification required")
        
        # Generate tokens
        access_token = self.create_access_token(
            data={
                "sub": user.id,
                "device_id": device_id,
                "scopes": user.scopes
            }
        )
        
        refresh_token = self.create_refresh_token(
            data={
                "sub": user.id,
                "device_id": device_id
            }
        )
        
        # Log authentication event
        await self.log_auth_event(
            user_id=user.id,
            device_id=device_id,
            event_type="login",
            ip_address=request.client.host
        )
        
        return AuthResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=self.access_token_expire.total_seconds()
        )
    
    def create_access_token(self, data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + self.access_token_expire
        to_encode.update({"exp": expire, "type": "access"})
        
        return jwt.encode(
            to_encode,
            self.secret_key,
            algorithm=self.algorithm
        )
```

### 3. Multi-Factor Authentication

```typescript
// Multi-factor authentication flow
class MFAManager {
    async setupMFA(userId: string, method: MFAMethod): Promise<MFASetup> {
        switch (method) {
            case 'totp':
                return this.setupTOTP(userId);
            case 'sms':
                return this.setupSMS(userId);
            case 'biometric':
                return this.setupBiometric(userId);
            case 'hardware_key':
                return this.setupHardwareKey(userId);
        }
    }
    
    private async setupTOTP(userId: string): Promise<TOTPSetup> {
        // Generate secret
        const secret = authenticator.generateSecret();
        
        // Generate QR code
        const qrCodeUrl = authenticator.keyuri(
            userId,
            'WildThing',
            secret
        );
        
        // Store encrypted secret
        await this.storage.storeMFASecret({
            userId,
            method: 'totp',
            secret: await this.encrypt(secret),
            createdAt: new Date()
        });
        
        return {
            method: 'totp',
            qrCode: await QRCode.toDataURL(qrCodeUrl),
            backupCodes: this.generateBackupCodes()
        };
    }
    
    async verifyMFA(
        userId: string,
        method: MFAMethod,
        code: string
    ): Promise<boolean> {
        const mfaConfig = await this.storage.getMFAConfig(userId, method);
        
        switch (method) {
            case 'totp':
                const secret = await this.decrypt(mfaConfig.secret);
                return authenticator.verify({
                    token: code,
                    secret: secret,
                    window: 2 // Allow 2 time windows
                });
                
            case 'biometric':
                return this.verifyBiometric(code, mfaConfig);
                
            case 'hardware_key':
                return this.verifyHardwareKey(code, mfaConfig);
        }
    }
}
```

## Authorization Architecture

### 1. Role-Based Access Control (RBAC)

```python
# Role and permission definitions
class Role(Enum):
    OWNER = "owner"          # Full access to all home data
    ADMIN = "admin"          # Manage users and settings
    MEMBER = "member"        # Read/write home data
    GUEST = "guest"          # Read-only access
    SERVICE = "service"      # API access for integrations

class Permission(Enum):
    # Entity permissions
    ENTITY_CREATE = "entity:create"
    ENTITY_READ = "entity:read"
    ENTITY_UPDATE = "entity:update"
    ENTITY_DELETE = "entity:delete"
    
    # User management
    USER_INVITE = "user:invite"
    USER_REMOVE = "user:remove"
    USER_UPDATE = "user:update"
    
    # System permissions
    SYSTEM_ADMIN = "system:admin"
    SYNC_FORCE = "sync:force"
    ANALYTICS_VIEW = "analytics:view"

# Role-permission mapping
ROLE_PERMISSIONS = {
    Role.OWNER: [p for p in Permission],  # All permissions
    Role.ADMIN: [
        Permission.ENTITY_CREATE,
        Permission.ENTITY_READ,
        Permission.ENTITY_UPDATE,
        Permission.ENTITY_DELETE,
        Permission.USER_INVITE,
        Permission.USER_REMOVE,
        Permission.USER_UPDATE,
        Permission.ANALYTICS_VIEW
    ],
    Role.MEMBER: [
        Permission.ENTITY_CREATE,
        Permission.ENTITY_READ,
        Permission.ENTITY_UPDATE,
        Permission.ANALYTICS_VIEW
    ],
    Role.GUEST: [
        Permission.ENTITY_READ
    ],
    Role.SERVICE: [
        Permission.ENTITY_READ,
        Permission.ENTITY_UPDATE
    ]
}

class AuthorizationService:
    async def check_permission(
        self,
        user_id: str,
        resource_id: str,
        permission: Permission
    ) -> bool:
        # Get user's role for resource
        user_role = await self.get_user_role(user_id, resource_id)
        
        # Check if role has permission
        if permission in ROLE_PERMISSIONS.get(user_role, []):
            return True
        
        # Check custom permissions
        custom_perms = await self.get_custom_permissions(user_id, resource_id)
        return permission in custom_perms
    
    async def check_entity_access(
        self,
        user_id: str,
        entity_id: str,
        operation: str
    ) -> bool:
        # Get entity
        entity = await self.storage.get_entity(entity_id)
        if not entity:
            return False
        
        # Owner always has access
        if entity.user_id == user_id:
            return True
        
        # Check home-level permissions
        home_id = await self.get_entity_home(entity_id)
        permission = Permission(f"entity:{operation}")
        
        return await self.check_permission(user_id, home_id, permission)
```

### 2. Attribute-Based Access Control (ABAC)

```typescript
// Fine-grained access control
interface AccessPolicy {
    id: string;
    name: string;
    effect: 'allow' | 'deny';
    subjects: PolicySubject[];
    resources: PolicyResource[];
    actions: string[];
    conditions?: PolicyCondition[];
}

interface PolicySubject {
    type: 'user' | 'role' | 'group';
    id: string;
    attributes?: Record<string, any>;
}

interface PolicyResource {
    type: 'entity' | 'home' | 'device';
    id?: string;
    attributes?: Record<string, any>;
}

interface PolicyCondition {
    type: 'time' | 'location' | 'device' | 'custom';
    operator: 'equals' | 'contains' | 'between' | 'matches';
    value: any;
}

class ABACEngine {
    async evaluateAccess(
        subject: Subject,
        resource: Resource,
        action: string,
        context: Context
    ): Promise<boolean> {
        // Get applicable policies
        const policies = await this.findApplicablePolicies(
            subject,
            resource,
            action
        );
        
        // Evaluate policies in order
        for (const policy of policies) {
            if (await this.evaluatePolicy(policy, subject, resource, action, context)) {
                return policy.effect === 'allow';
            }
        }
        
        // Default deny
        return false;
    }
    
    private async evaluatePolicy(
        policy: AccessPolicy,
        subject: Subject,
        resource: Resource,
        action: string,
        context: Context
    ): Promise<boolean> {
        // Check subject match
        if (!this.matchesSubject(policy.subjects, subject)) {
            return false;
        }
        
        // Check resource match
        if (!this.matchesResource(policy.resources, resource)) {
            return false;
        }
        
        // Check action match
        if (!policy.actions.includes(action)) {
            return false;
        }
        
        // Evaluate conditions
        if (policy.conditions) {
            for (const condition of policy.conditions) {
                if (!await this.evaluateCondition(condition, context)) {
                    return false;
                }
            }
        }
        
        return true;
    }
}
```

## Encryption Architecture

### 1. Data Encryption

```swift
// Client-side encryption
class EncryptionManager {
    private let keychain = KeychainManager()
    
    // Encryption key hierarchy
    private var masterKey: SymmetricKey?
    private var dataEncryptionKeys: [String: SymmetricKey] = [:]
    
    func initializeEncryption() throws {
        // Generate or retrieve master key
        if let existingKey = try keychain.retrieveMasterKey() {
            self.masterKey = existingKey
        } else {
            self.masterKey = SymmetricKey(size: .bits256)
            try keychain.storeMasterKey(masterKey!)
        }
        
        // Derive data encryption keys
        deriveDataKeys()
    }
    
    func encryptEntity(_ entity: HomeEntity) throws -> EncryptedEntity {
        let dek = try getDataEncryptionKey(for: entity.entityType)
        
        // Encrypt content
        let plaintext = try JSONEncoder().encode(entity.content)
        let sealedBox = try AES.GCM.seal(plaintext, using: dek)
        
        return EncryptedEntity(
            id: entity.id,
            version: entity.version,
            entityType: entity.entityType,
            encryptedContent: sealedBox.combined!,
            nonce: sealedBox.nonce.data,
            tag: sealedBox.tag.data,
            keyId: dek.identifier
        )
    }
    
    func decryptEntity(_ encrypted: EncryptedEntity) throws -> HomeEntity {
        let dek = try getDataEncryptionKey(for: encrypted.entityType)
        
        // Reconstruct sealed box
        let sealedBox = try AES.GCM.SealedBox(
            nonce: AES.GCM.Nonce(data: encrypted.nonce),
            ciphertext: encrypted.encryptedContent,
            tag: encrypted.tag
        )
        
        // Decrypt
        let plaintext = try AES.GCM.open(sealedBox, using: dek)
        let content = try JSONDecoder().decode(
            [String: AnyCodable].self,
            from: plaintext
        )
        
        return HomeEntity(
            id: encrypted.id,
            version: encrypted.version,
            entityType: encrypted.entityType,
            content: content
        )
    }
}
```

### 2. Transport Security

```python
# TLS configuration and certificate pinning
class TransportSecurity:
    def __init__(self):
        self.min_tls_version = ssl.TLSVersion.TLSv1_3
        self.cipher_suites = [
            'TLS_AES_256_GCM_SHA384',
            'TLS_CHACHA20_POLY1305_SHA256',
            'TLS_AES_128_GCM_SHA256'
        ]
        self.pinned_certificates = self.load_pinned_certs()
    
    def create_ssl_context(self) -> ssl.SSLContext:
        context = ssl.create_default_context()
        context.minimum_version = self.min_tls_version
        context.set_ciphers(':'.join(self.cipher_suites))
        
        # Certificate pinning
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(cadata=self.pinned_certificates)
        
        return context
    
    async def verify_certificate(self, cert: x509.Certificate) -> bool:
        # Verify certificate chain
        if not self.verify_chain(cert):
            return False
        
        # Check certificate pinning
        cert_fingerprint = cert.fingerprint(hashes.SHA256())
        if cert_fingerprint not in self.pinned_fingerprints:
            logger.warning(f"Certificate pinning failed: {cert_fingerprint}")
            return False
        
        # Check certificate transparency
        if not await self.verify_ct_logs(cert):
            return False
        
        return True
```

### 3. End-to-End Encryption (E2EE)

```typescript
// Optional E2EE for sensitive data
class E2EEManager {
    private userKeyPairs: Map<string, CryptoKeyPair> = new Map();
    
    async setupE2EE(userId: string): Promise<E2EESetup> {
        // Generate user keypair
        const keyPair = await crypto.subtle.generateKey(
            {
                name: 'RSA-OAEP',
                modulusLength: 4096,
                publicExponent: new Uint8Array([1, 0, 1]),
                hash: 'SHA-256'
            },
            true,
            ['encrypt', 'decrypt']
        );
        
        // Store private key securely
        await this.secureStorage.storePrivateKey(userId, keyPair.privateKey);
        
        // Export public key for sharing
        const publicKeyData = await crypto.subtle.exportKey(
            'spki',
            keyPair.publicKey
        );
        
        return {
            userId,
            publicKey: btoa(String.fromCharCode(...new Uint8Array(publicKeyData))),
            algorithm: 'RSA-OAEP-256'
        };
    }
    
    async encryptForUser(
        data: any,
        recipientUserId: string
    ): Promise<EncryptedMessage> {
        // Get recipient's public key
        const recipientKey = await this.getPublicKey(recipientUserId);
        
        // Generate ephemeral AES key
        const aesKey = await crypto.subtle.generateKey(
            { name: 'AES-GCM', length: 256 },
            true,
            ['encrypt', 'decrypt']
        );
        
        // Encrypt data with AES
        const iv = crypto.getRandomValues(new Uint8Array(12));
        const encryptedData = await crypto.subtle.encrypt(
            { name: 'AES-GCM', iv },
            aesKey,
            new TextEncoder().encode(JSON.stringify(data))
        );
        
        // Encrypt AES key with recipient's public key
        const encryptedKey = await crypto.subtle.encrypt(
            { name: 'RSA-OAEP' },
            recipientKey,
            await crypto.subtle.exportKey('raw', aesKey)
        );
        
        return {
            recipientId: recipientUserId,
            encryptedKey: btoa(String.fromCharCode(...new Uint8Array(encryptedKey))),
            encryptedData: btoa(String.fromCharCode(...new Uint8Array(encryptedData))),
            iv: btoa(String.fromCharCode(...iv)),
            algorithm: 'hybrid-rsa-aes'
        };
    }
}
```

## Security Headers and Policies

### 1. HTTP Security Headers

```python
# Security headers middleware
class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app
        
    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            async def send_wrapper(message):
                if message['type'] == 'http.response.start':
                    headers = MutableHeaders(scope=message)
                    
                    # Security headers
                    headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
                    headers['X-Content-Type-Options'] = 'nosniff'
                    headers['X-Frame-Options'] = 'DENY'
                    headers['X-XSS-Protection'] = '1; mode=block'
                    headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
                    headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
                    
                    # Content Security Policy
                    headers['Content-Security-Policy'] = "; ".join([
                        "default-src 'self'",
                        "script-src 'self' 'nonce-{nonce}'",
                        "style-src 'self' 'unsafe-inline'",
                        "img-src 'self' data: https:",
                        "font-src 'self'",
                        "connect-src 'self' wss://funkygibbon.com",
                        "frame-ancestors 'none'",
                        "base-uri 'self'",
                        "form-action 'self'"
                    ])
                    
                await send(message)
            
            await self.app(scope, receive, send_wrapper)
        else:
            await self.app(scope, receive, send)
```

### 2. CORS Configuration

```typescript
// CORS policy configuration
const corsOptions: CorsOptions = {
    origin: (origin, callback) => {
        // Whitelist check
        const whitelist = [
            'https://app.wildthing.com',
            'https://admin.wildthing.com',
            'wildthing://app'  // Mobile app
        ];
        
        if (!origin || whitelist.includes(origin)) {
            callback(null, true);
        } else {
            callback(new Error('Not allowed by CORS'));
        }
    },
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: [
        'Content-Type',
        'Authorization',
        'X-Device-ID',
        'X-Request-ID',
        'X-API-Version'
    ],
    exposedHeaders: [
        'X-RateLimit-Limit',
        'X-RateLimit-Remaining',
        'X-RateLimit-Reset'
    ],
    maxAge: 86400  // 24 hours
};
```

## Input Validation and Sanitization

### 1. Request Validation

```python
# Comprehensive input validation
from pydantic import BaseModel, validator, constr, conint
import bleach
import re

class EntityCreateRequest(BaseModel):
    entity_type: EntityType
    name: constr(min_length=1, max_length=100, strip_whitespace=True)
    content: Dict[str, Any]
    location: Optional[UUID] = None
    
    @validator('name')
    def validate_name(cls, v):
        # Prevent XSS
        cleaned = bleach.clean(v, tags=[], strip=True)
        if cleaned != v:
            raise ValueError("Invalid characters in name")
        
        # Prevent SQL injection
        if re.search(r'[;\'"\-\-]|(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION)\b)', v, re.IGNORECASE):
            raise ValueError("Invalid name format")
        
        return v
    
    @validator('content')
    def validate_content(cls, v):
        # Deep validation of content
        def validate_value(value, path=""):
            if isinstance(value, str):
                # String validation
                if len(value) > 10000:
                    raise ValueError(f"String too long at {path}")
                # Sanitize HTML
                return bleach.clean(value, tags=['b', 'i', 'u'], strip=True)
            elif isinstance(value, (int, float)):
                # Number validation
                if abs(value) > 1e9:
                    raise ValueError(f"Number too large at {path}")
                return value
            elif isinstance(value, list):
                # Array validation
                if len(value) > 1000:
                    raise ValueError(f"Array too large at {path}")
                return [validate_value(item, f"{path}[{i}]") for i, item in enumerate(value)]
            elif isinstance(value, dict):
                # Object validation
                if len(value) > 100:
                    raise ValueError(f"Object too large at {path}")
                return {k: validate_value(v, f"{path}.{k}") for k, v in value.items()}
            else:
                raise ValueError(f"Invalid type at {path}")
        
        return validate_value(v)
```

### 2. Output Sanitization

```typescript
// Output encoding and sanitization
class OutputSanitizer {
    sanitizeForJSON(data: any): any {
        if (typeof data === 'string') {
            // Escape special characters
            return data
                .replace(/\\/g, '\\\\')
                .replace(/"/g, '\\"')
                .replace(/\n/g, '\\n')
                .replace(/\r/g, '\\r')
                .replace(/\t/g, '\\t');
        } else if (Array.isArray(data)) {
            return data.map(item => this.sanitizeForJSON(item));
        } else if (typeof data === 'object' && data !== null) {
            const sanitized: any = {};
            for (const [key, value] of Object.entries(data)) {
                sanitized[this.sanitizeForJSON(key)] = this.sanitizeForJSON(value);
            }
            return sanitized;
        }
        return data;
    }
    
    sanitizeForHTML(text: string): string {
        const entityMap: Record<string, string> = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
            '/': '&#x2F;',
            '`': '&#x60;',
            '=': '&#x3D;'
        };
        
        return text.replace(/[&<>"'`=\/]/g, (s) => entityMap[s]);
    }
}
```

## Rate Limiting and DDoS Protection

### 1. Rate Limiting Implementation

```python
# Advanced rate limiting with sliding window
class RateLimiter:
    def __init__(self, redis: Redis):
        self.redis = redis
        self.limits = {
            'default': (100, 60),      # 100 requests per minute
            'auth': (5, 300),          # 5 auth attempts per 5 minutes
            'sync': (10, 60),          # 10 sync requests per minute
            'create': (50, 60),        # 50 creates per minute
            'analytics': (20, 3600)    # 20 analytics requests per hour
        }
    
    async def check_rate_limit(
        self,
        key: str,
        category: str = 'default'
    ) -> RateLimitResult:
        limit, window = self.limits.get(category, self.limits['default'])
        
        # Sliding window algorithm
        now = time.time()
        window_start = now - window
        
        # Remove old entries
        await self.redis.zremrangebyscore(key, 0, window_start)
        
        # Count requests in window
        current_count = await self.redis.zcard(key)
        
        if current_count >= limit:
            # Calculate retry after
            oldest = await self.redis.zrange(key, 0, 0, withscores=True)
            if oldest:
                retry_after = int(oldest[0][1] + window - now)
            else:
                retry_after = window
            
            return RateLimitResult(
                allowed=False,
                limit=limit,
                remaining=0,
                reset_at=int(now + retry_after),
                retry_after=retry_after
            )
        
        # Add current request
        await self.redis.zadd(key, {str(uuid.uuid4()): now})
        await self.redis.expire(key, window + 1)
        
        return RateLimitResult(
            allowed=True,
            limit=limit,
            remaining=limit - current_count - 1,
            reset_at=int(now + window)
        )
```

### 2. DDoS Protection

```typescript
// DDoS protection layer
class DDoSProtection {
    private readonly blacklist = new Set<string>();
    private readonly requestCounts = new Map<string, RequestInfo>();
    
    async checkRequest(
        ip: string,
        userAgent: string,
        path: string
    ): Promise<boolean> {
        // Check blacklist
        if (this.blacklist.has(ip)) {
            return false;
        }
        
        // Check request patterns
        const info = this.requestCounts.get(ip) || {
            count: 0,
            firstSeen: Date.now(),
            paths: new Set(),
            userAgents: new Set()
        };
        
        info.count++;
        info.paths.add(path);
        info.userAgents.add(userAgent);
        
        // Detect suspicious patterns
        if (this.isSuspicious(info)) {
            this.blacklist.add(ip);
            await this.notifySecurityTeam(ip, info);
            return false;
        }
        
        this.requestCounts.set(ip, info);
        return true;
    }
    
    private isSuspicious(info: RequestInfo): boolean {
        const duration = Date.now() - info.firstSeen;
        const requestsPerSecond = info.count / (duration / 1000);
        
        // High request rate
        if (requestsPerSecond > 10) return true;
        
        // Too many different user agents (bot behavior)
        if (info.userAgents.size > 5) return true;
        
        // Scanning behavior
        if (info.paths.size > 50 && duration < 60000) return true;
        
        return false;
    }
}
```

## Audit Logging and Monitoring

### 1. Comprehensive Audit Logging

```python
# Audit logging system
class AuditLogger:
    def __init__(self, storage: AuditStorage):
        self.storage = storage
        
    async def log_event(
        self,
        event_type: str,
        user_id: str,
        resource_id: Optional[str] = None,
        action: Optional[str] = None,
        result: str = 'success',
        metadata: Optional[Dict] = None
    ):
        event = AuditEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            event_type=event_type,
            user_id=user_id,
            device_id=context.device_id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            resource_id=resource_id,
            action=action,
            result=result,
            metadata=metadata or {},
            
            # Security context
            session_id=context.session_id,
            auth_method=context.auth_method,
            risk_score=await self.calculate_risk_score(context)
        )
        
        # Store event
        await self.storage.store_event(event)
        
        # Real-time analysis
        if event.risk_score > 0.7:
            await self.trigger_security_alert(event)
    
    async def calculate_risk_score(self, context: Context) -> float:
        score = 0.0
        
        # New device
        if await self.is_new_device(context.user_id, context.device_id):
            score += 0.2
        
        # Unusual location
        if await self.is_unusual_location(context.user_id, context.ip_address):
            score += 0.3
        
        # Time anomaly
        if self.is_unusual_time(context.user_id, context.timestamp):
            score += 0.2
        
        # High-value operation
        if context.action in ['delete', 'export', 'admin']:
            score += 0.2
        
        # Failed auth attempts
        recent_failures = await self.get_recent_auth_failures(context.user_id)
        if recent_failures > 3:
            score += 0.3
        
        return min(score, 1.0)
```

### 2. Security Monitoring

```typescript
// Real-time security monitoring
class SecurityMonitor {
    private readonly alerts: SecurityAlert[] = [];
    private readonly thresholds = {
        failedLogins: 5,
        suspiciousActivity: 3,
        dataExfiltration: 1000,  // entities
        privilegeEscalation: 1
    };
    
    async monitorActivity(event: SecurityEvent) {
        // Pattern detection
        const patterns = await this.detectPatterns(event);
        
        for (const pattern of patterns) {
            if (this.isThresholdExceeded(pattern)) {
                const alert = await this.createAlert(pattern, event);
                await this.handleAlert(alert);
            }
        }
    }
    
    private async detectPatterns(event: SecurityEvent): Promise<Pattern[]> {
        const patterns: Pattern[] = [];
        
        // Failed login attempts
        if (event.type === 'auth_failed') {
            const count = await this.countRecentEvents(
                event.userId,
                'auth_failed',
                300  // 5 minutes
            );
            
            if (count >= this.thresholds.failedLogins) {
                patterns.push({
                    type: 'brute_force',
                    severity: 'high',
                    count
                });
            }
        }
        
        // Data exfiltration
        if (event.type === 'entity_read') {
            const count = await this.countRecentEvents(
                event.userId,
                'entity_read',
                3600  // 1 hour
            );
            
            if (count >= this.thresholds.dataExfiltration) {
                patterns.push({
                    type: 'data_exfiltration',
                    severity: 'critical',
                    count
                });
            }
        }
        
        return patterns;
    }
    
    private async handleAlert(alert: SecurityAlert) {
        // Log alert
        await this.logAlert(alert);
        
        // Take automatic action
        switch (alert.severity) {
            case 'critical':
                await this.blockUser(alert.userId);
                await this.notifySecurityTeam(alert);
                break;
            case 'high':
                await this.requireMFA(alert.userId);
                await this.notifyUser(alert.userId, alert);
                break;
            case 'medium':
                await this.increaseMonitoring(alert.userId);
                break;
        }
    }
}
```

## Security Best Practices

### 1. Secure Development

```yaml
Development Security:
  Code Review:
    - All PRs require security review
    - Automated SAST scanning
    - Dependency vulnerability checks
    
  Secrets Management:
    - No secrets in code
    - Use environment variables
    - Rotate keys regularly
    
  Testing:
    - Security test suite
    - Penetration testing
    - Fuzzing for inputs

```

### 2. Deployment Security

```yaml
Production Security:
  Infrastructure:
    - Network segmentation
    - Firewall rules
    - VPN access only
    
  Container Security:
    - Minimal base images
    - Non-root users
    - Read-only filesystems
    
  Monitoring:
    - 24/7 SOC monitoring
    - Automated alerting
    - Incident response plan
```

### 3. Compliance

```yaml
Compliance Standards:
  Privacy:
    - GDPR compliance
    - CCPA compliance
    - Data minimization
    
  Security:
    - SOC 2 Type II
    - ISO 27001
    - OWASP Top 10
    
  Industry:
    - PCI DSS (if payment)
    - HIPAA (if health data)
    - FedRAMP (if government)
```

## Incident Response

### Response Plan

```python
class IncidentResponse:
    async def handle_incident(self, incident: SecurityIncident):
        # 1. Detect and Analysis
        severity = await self.assess_severity(incident)
        scope = await self.determine_scope(incident)
        
        # 2. Containment
        if severity >= Severity.HIGH:
            await self.immediate_containment(incident)
        
        # 3. Eradication
        await self.remove_threat(incident)
        
        # 4. Recovery
        await self.restore_services(incident)
        
        # 5. Post-Incident
        await self.document_lessons_learned(incident)
        await self.update_security_controls(incident)
```

## Conclusion

This security architecture provides:

1. **Strong Authentication** with device certificates and MFA
2. **Granular Authorization** with RBAC and ABAC
3. **Data Protection** with encryption at rest and in transit
4. **Network Security** with TLS 1.3 and certificate pinning
5. **Application Security** with input validation and output encoding
6. **Monitoring and Auditing** for threat detection
7. **Incident Response** procedures

The defense-in-depth approach ensures multiple layers of protection for user data and system integrity.
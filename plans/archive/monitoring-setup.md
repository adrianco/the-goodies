# Monitoring and Observability Setup - The Goodies Platform

## Overview

This guide outlines the comprehensive monitoring and observability strategy for The Goodies platform, covering metrics, logging, tracing, and alerting for both FunkyGibbon API and WildThing SDK.

## Monitoring Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Monitoring Stack                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐│
│  │ Prometheus  │  │   Grafana   │  │    Loki     │  │   Jaeger   ││
│  │  (Metrics)  │  │(Dashboards) │  │   (Logs)    │  │  (Traces)  ││
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────┬──────┘│
│         │                 │                 │                │       │
│         └─────────────────┴─────────────────┴────────────────┘      │
│                                    │                                 │
├────────────────────────────────────┼─────────────────────────────────┤
│                                    │                                 │
│  ┌─────────────┐  ┌─────────────┐ │ ┌─────────────┐  ┌────────────┐│
│  │ FunkyGibbon │  │ PostgreSQL  │ │ │    Redis    │  │   Nginx    ││
│  │     API     │  │  Exporter   │ │ │  Exporter   │  │  Exporter  ││
│  └─────────────┘  └─────────────┘ │ └─────────────┘  └────────────┘│
│                                    │                                 │
│  ┌─────────────────────────────────┴──────────────────────────────┐ │
│  │                        Alert Manager                            │ │
│  │                    (PagerDuty, Slack, Email)                   │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## Metrics Collection

### Prometheus Configuration

#### prometheus.yml
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    environment: 'production'
    region: 'us-east-1'

# Alertmanager configuration
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093

# Load rules
rule_files:
  - "alerts/*.yml"
  - "recording_rules/*.yml"

# Scrape configurations
scrape_configs:
  # FunkyGibbon API metrics
  - job_name: 'funkygibbon-api'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - production
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: true
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_path]
        action: replace
        target_label: __metrics_path__
        regex: (.+)
      - source_labels: [__address__, __meta_kubernetes_pod_annotation_prometheus_io_port]
        action: replace
        regex: ([^:]+)(?::\d+)?;(\d+)
        replacement: $1:$2
        target_label: __address__

  # PostgreSQL exporter
  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']
    params:
      query: ['custom_queries.yml']

  # Redis exporter
  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']

  # Node exporter
  - job_name: 'node'
    kubernetes_sd_configs:
      - role: node
    relabel_configs:
      - action: labelmap
        regex: __meta_kubernetes_node_label_(.+)

  # Kubernetes metrics
  - job_name: 'kubernetes-apiservers'
    kubernetes_sd_configs:
      - role: endpoints
    scheme: https
    tls_config:
      ca_file: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
    bearer_token_file: /var/run/secrets/kubernetes.io/serviceaccount/token
    relabel_configs:
      - source_labels: [__meta_kubernetes_namespace, __meta_kubernetes_service_name, __meta_kubernetes_endpoint_port_name]
        action: keep
        regex: default;kubernetes;https
```

### Application Metrics

#### FunkyGibbon Metrics Endpoint
```go
// metrics/prometheus.go
package metrics

import (
    "github.com/prometheus/client_golang/prometheus"
    "github.com/prometheus/client_golang/prometheus/promauto"
)

var (
    // HTTP metrics
    httpRequestsTotal = promauto.NewCounterVec(
        prometheus.CounterOpts{
            Name: "funkygibbon_http_requests_total",
            Help: "Total number of HTTP requests",
        },
        []string{"method", "path", "status"},
    )
    
    httpRequestDuration = promauto.NewHistogramVec(
        prometheus.HistogramOpts{
            Name: "funkygibbon_http_request_duration_seconds",
            Help: "HTTP request latency",
            Buckets: prometheus.DefBuckets,
        },
        []string{"method", "path"},
    )
    
    // Business metrics
    userRegistrations = promauto.NewCounter(
        prometheus.CounterOpts{
            Name: "funkygibbon_user_registrations_total",
            Help: "Total number of user registrations",
        },
    )
    
    activeUsers = promauto.NewGauge(
        prometheus.GaugeOpts{
            Name: "funkygibbon_active_users",
            Help: "Number of active users",
        },
    )
    
    // Database metrics
    dbConnectionsActive = promauto.NewGaugeVec(
        prometheus.GaugeOpts{
            Name: "funkygibbon_db_connections_active",
            Help: "Active database connections",
        },
        []string{"db_name"},
    )
    
    dbQueryDuration = promauto.NewHistogramVec(
        prometheus.HistogramOpts{
            Name: "funkygibbon_db_query_duration_seconds",
            Help: "Database query execution time",
            Buckets: []float64{.001, .005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5},
        },
        []string{"query_type", "table"},
    )
)
```

### Custom Metrics

#### Recording Rules
```yaml
# recording_rules/api_rules.yml
groups:
  - name: api_rules
    interval: 30s
    rules:
      # Request rate
      - record: funkygibbon:http_request_rate_5m
        expr: rate(funkygibbon_http_requests_total[5m])
      
      # Error rate
      - record: funkygibbon:http_error_rate_5m
        expr: rate(funkygibbon_http_requests_total{status=~"5.."}[5m])
      
      # P95 latency
      - record: funkygibbon:http_latency_p95_5m
        expr: histogram_quantile(0.95, rate(funkygibbon_http_request_duration_seconds_bucket[5m]))
      
      # Database connection utilization
      - record: funkygibbon:db_connection_utilization
        expr: funkygibbon_db_connections_active / funkygibbon_db_connections_max
```

## Logging Architecture

### Structured Logging

#### Application Logging Configuration
```go
// logging/logger.go
package logging

import (
    "go.uber.org/zap"
    "go.uber.org/zap/zapcore"
)

func NewLogger(env string) (*zap.Logger, error) {
    var config zap.Config
    
    if env == "production" {
        config = zap.NewProductionConfig()
        config.EncoderConfig.TimeKey = "@timestamp"
        config.EncoderConfig.EncodeTime = zapcore.ISO8601TimeEncoder
    } else {
        config = zap.NewDevelopmentConfig()
    }
    
    // Add custom fields
    config.InitialFields = map[string]interface{}{
        "service": "funkygibbon",
        "version": "1.0.0",
        "env":     env,
    }
    
    return config.Build()
}

// Structured logging example
logger.Info("user login successful",
    zap.String("user_id", userID),
    zap.String("ip", clientIP),
    zap.Duration("duration", duration),
    zap.String("trace_id", traceID),
)
```

### Log Aggregation with Loki

#### Loki Configuration
```yaml
# loki-config.yml
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9096

common:
  path_prefix: /tmp/loki
  storage:
    filesystem:
      chunks_directory: /tmp/loki/chunks
      rules_directory: /tmp/loki/rules
  replication_factor: 1
  ring:
    instance_addr: 127.0.0.1
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

ruler:
  alertmanager_url: http://alertmanager:9093

analytics:
  reporting_enabled: false
```

#### Promtail Configuration
```yaml
# promtail-config.yml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  # Kubernetes pods
  - job_name: kubernetes-pods
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels:
          - __meta_kubernetes_pod_controller_name
        regex: ([0-9a-z-.]+?)(-[0-9a-f]{8,10})?
        action: replace
        target_label: __tmp_controller_name
      - source_labels:
          - __meta_kubernetes_pod_label_app
        action: replace
        target_label: app
      - source_labels:
          - __meta_kubernetes_pod_annotation_prometheus_io_scrape
        action: keep
        regex: true
    pipeline_stages:
      - json:
          expressions:
            timestamp: "@timestamp"
            level: level
            message: msg
            trace_id: trace_id
      - labels:
          level:
          app:
      - timestamp:
          source: timestamp
          format: RFC3339
```

## Distributed Tracing

### Jaeger Setup

#### Docker Compose
```yaml
jaeger:
  image: jaegertracing/all-in-one:latest
  environment:
    - COLLECTOR_ZIPKIN_HTTP_PORT=9411
    - COLLECTOR_OTLP_ENABLED=true
  ports:
    - "5775:5775/udp"
    - "6831:6831/udp"
    - "6832:6832/udp"
    - "5778:5778"
    - "16686:16686"
    - "14250:14250"
    - "14268:14268"
    - "14269:14269"
    - "4317:4317"
    - "4318:4318"
    - "9411:9411"
```

#### Application Instrumentation
```go
// tracing/tracer.go
package tracing

import (
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/exporters/jaeger"
    "go.opentelemetry.io/otel/sdk/trace"
)

func InitTracer(serviceName, jaegerEndpoint string) (*trace.TracerProvider, error) {
    exporter, err := jaeger.New(
        jaeger.WithCollectorEndpoint(jaeger.WithEndpoint(jaegerEndpoint)),
    )
    if err != nil {
        return nil, err
    }
    
    tp := trace.NewTracerProvider(
        trace.WithBatcher(exporter),
        trace.WithResource(
            resource.NewWithAttributes(
                semconv.SchemaURL,
                semconv.ServiceNameKey.String(serviceName),
                semconv.ServiceVersionKey.String("1.0.0"),
            ),
        ),
    )
    
    otel.SetTracerProvider(tp)
    return tp, nil
}

// Usage in handler
func HandleRequest(ctx context.Context) {
    ctx, span := otel.Tracer("funkygibbon").Start(ctx, "HandleRequest")
    defer span.End()
    
    // Add attributes
    span.SetAttributes(
        attribute.String("user.id", userID),
        attribute.String("request.id", requestID),
    )
    
    // Continue processing...
}
```

## Grafana Dashboards

### API Performance Dashboard

```json
{
  "dashboard": {
    "title": "FunkyGibbon API Performance",
    "panels": [
      {
        "title": "Request Rate",
        "targets": [
          {
            "expr": "sum(rate(funkygibbon_http_requests_total[5m])) by (method)"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Error Rate",
        "targets": [
          {
            "expr": "sum(rate(funkygibbon_http_requests_total{status=~\"5..\"}[5m])) / sum(rate(funkygibbon_http_requests_total[5m]))"
          }
        ],
        "type": "stat"
      },
      {
        "title": "Response Time (P95)",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, sum(rate(funkygibbon_http_request_duration_seconds_bucket[5m])) by (le))"
          }
        ],
        "type": "gauge"
      },
      {
        "title": "Active Database Connections",
        "targets": [
          {
            "expr": "funkygibbon_db_connections_active"
          }
        ],
        "type": "graph"
      }
    ]
  }
}
```

### Infrastructure Dashboard

```json
{
  "dashboard": {
    "title": "Infrastructure Overview",
    "panels": [
      {
        "title": "CPU Usage",
        "targets": [
          {
            "expr": "100 - (avg by (instance) (irate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)"
          }
        ]
      },
      {
        "title": "Memory Usage",
        "targets": [
          {
            "expr": "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100"
          }
        ]
      },
      {
        "title": "Disk I/O",
        "targets": [
          {
            "expr": "rate(node_disk_io_time_seconds_total[5m])"
          }
        ]
      },
      {
        "title": "Network Traffic",
        "targets": [
          {
            "expr": "rate(node_network_receive_bytes_total[5m])",
            "legendFormat": "Receive"
          },
          {
            "expr": "rate(node_network_transmit_bytes_total[5m])",
            "legendFormat": "Transmit"
          }
        ]
      }
    ]
  }
}
```

## Alerting Configuration

### Alert Rules

```yaml
# alerts/api_alerts.yml
groups:
  - name: api_alerts
    rules:
      # High error rate
      - alert: HighErrorRate
        expr: funkygibbon:http_error_rate_5m > 0.05
        for: 5m
        labels:
          severity: critical
          team: backend
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value | humanizePercentage }} for the last 5 minutes"
          
      # High response time
      - alert: HighResponseTime
        expr: funkygibbon:http_latency_p95_5m > 1
        for: 10m
        labels:
          severity: warning
          team: backend
        annotations:
          summary: "High API response time"
          description: "P95 response time is {{ $value }}s"
          
      # Database connection pool exhaustion
      - alert: DatabaseConnectionPoolExhaustion
        expr: funkygibbon:db_connection_utilization > 0.9
        for: 5m
        labels:
          severity: critical
          team: backend
        annotations:
          summary: "Database connection pool nearly exhausted"
          description: "Connection pool utilization is {{ $value | humanizePercentage }}"
          
      # Pod restart
      - alert: PodRestartingTooOften
        expr: rate(kube_pod_container_status_restarts_total[15m]) > 0
        labels:
          severity: warning
        annotations:
          summary: "Pod restarting frequently"
          description: "Pod {{ $labels.pod }} has restarted {{ $value }} times"
```

### AlertManager Configuration

```yaml
# alertmanager.yml
global:
  resolve_timeout: 5m
  slack_api_url: 'YOUR_SLACK_WEBHOOK_URL'

route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'default'
  routes:
    - match:
        severity: critical
      receiver: pagerduty-critical
      continue: true
    - match:
        severity: warning
      receiver: slack-warnings

receivers:
  - name: 'default'
    slack_configs:
      - channel: '#alerts'
        title: 'FunkyGibbon Alert'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'
        
  - name: 'pagerduty-critical'
    pagerduty_configs:
      - service_key: 'YOUR_PAGERDUTY_SERVICE_KEY'
        description: '{{ .GroupLabels.alertname }}'
        
  - name: 'slack-warnings'
    slack_configs:
      - channel: '#alerts-warning'
        send_resolved: true
```

## Performance Monitoring

### Application Performance Monitoring (APM)

#### New Relic Integration
```go
// newrelic/init.go
import "github.com/newrelic/go-agent/v3/newrelic"

func InitNewRelic() (*newrelic.Application, error) {
    app, err := newrelic.NewApplication(
        newrelic.ConfigAppName("FunkyGibbon API"),
        newrelic.ConfigLicense(os.Getenv("NEW_RELIC_LICENSE_KEY")),
        newrelic.ConfigDistributedTracerEnabled(true),
        newrelic.ConfigCodeLevelMetricsEnabled(true),
    )
    return app, err
}

// Middleware
func NewRelicMiddleware(app *newrelic.Application) gin.HandlerFunc {
    return func(c *gin.Context) {
        txn := app.StartTransaction(c.Request.URL.Path)
        defer txn.End()
        
        c.Set("newrelic_txn", txn)
        c.Next()
        
        txn.SetWebResponse(c.Writer)
        txn.SetWebRequest(c.Request)
    }
}
```

### Database Performance

#### Query Performance Monitoring
```sql
-- Slow query log
ALTER DATABASE funkygibbon SET log_min_duration_statement = 100;

-- Query stats extension
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Top slow queries
SELECT 
    query,
    mean_exec_time,
    calls,
    total_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

## Health Checks

### Application Health Endpoints

```go
// health/checks.go
type HealthChecker struct {
    db    *sql.DB
    redis *redis.Client
}

func (h *HealthChecker) LivenessHandler(w http.ResponseWriter, r *http.Request) {
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(map[string]string{
        "status": "ok",
        "timestamp": time.Now().Format(time.RFC3339),
    })
}

func (h *HealthChecker) ReadinessHandler(w http.ResponseWriter, r *http.Request) {
    checks := map[string]bool{
        "database": h.checkDatabase(),
        "redis": h.checkRedis(),
        "disk_space": h.checkDiskSpace(),
    }
    
    allHealthy := true
    for _, healthy := range checks {
        if !healthy {
            allHealthy = false
            break
        }
    }
    
    status := http.StatusOK
    if !allHealthy {
        status = http.StatusServiceUnavailable
    }
    
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(status)
    json.NewEncoder(w).Encode(checks)
}
```

## SLIs, SLOs, and Error Budgets

### Service Level Indicators (SLIs)

```yaml
slis:
  - name: availability
    description: "Percentage of successful requests"
    query: |
      sum(rate(funkygibbon_http_requests_total{status!~"5.."}[5m]))
      /
      sum(rate(funkygibbon_http_requests_total[5m]))
      
  - name: latency
    description: "Percentage of requests faster than 500ms"
    query: |
      sum(rate(funkygibbon_http_request_duration_seconds_bucket{le="0.5"}[5m]))
      /
      sum(rate(funkygibbon_http_request_duration_seconds_count[5m]))
      
  - name: error_rate
    description: "Percentage of requests without errors"
    query: |
      1 - (
        sum(rate(funkygibbon_http_requests_total{status=~"5.."}[5m]))
        /
        sum(rate(funkygibbon_http_requests_total[5m]))
      )
```

### Service Level Objectives (SLOs)

```yaml
slos:
  - sli: availability
    target: 99.9  # Three nines
    window: 30d
    
  - sli: latency
    target: 95    # 95% of requests under 500ms
    window: 30d
    
  - sli: error_rate
    target: 99.5  # Less than 0.5% error rate
    window: 30d
```

### Error Budget Monitoring

```yaml
# Error budget alert
- alert: ErrorBudgetBurn
  expr: |
    (
      1 - (
        sum(rate(funkygibbon_http_requests_total{status!~"5.."}[1h]))
        /
        sum(rate(funkygibbon_http_requests_total[1h]))
      )
    ) > 0.001 * 14.4  # 14.4x burn rate
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Error budget burn rate too high"
    description: "At current burn rate, error budget will be exhausted in {{ $value }} hours"
```

## Cost Monitoring

### Cloud Cost Tracking

```yaml
# AWS Cost Explorer integration
- job_name: 'aws_costs'
  static_configs:
    - targets: ['aws-cost-exporter:9090']
  metrics_path: /metrics
  params:
    services: ['EC2', 'RDS', 'ElastiCache', 'S3']
    
# Cost alerts
- alert: HighCloudCosts
  expr: aws_daily_cost > 500
  labels:
    severity: warning
  annotations:
    summary: "Daily cloud costs exceeding budget"
    description: "Current daily cost: ${{ $value }}"
```

## Mobile SDK Monitoring

### WildThing SDK Metrics

```swift
// Analytics/WildThingAnalytics.swift
import Foundation

class WildThingAnalytics {
    static let shared = WildThingAnalytics()
    
    func trackEvent(_ event: String, properties: [String: Any] = [:]) {
        var enrichedProperties = properties
        enrichedProperties["sdk_version"] = WildThing.version
        enrichedProperties["platform"] = UIDevice.current.systemName
        enrichedProperties["platform_version"] = UIDevice.current.systemVersion
        enrichedProperties["timestamp"] = Date().timeIntervalSince1970
        
        // Send to analytics backend
        analyticsClient.track(event: event, properties: enrichedProperties)
    }
    
    func trackAPICall(endpoint: String, duration: TimeInterval, statusCode: Int) {
        trackEvent("api_call", properties: [
            "endpoint": endpoint,
            "duration_ms": Int(duration * 1000),
            "status_code": statusCode,
            "success": (200...299).contains(statusCode)
        ])
    }
}
```

## Incident Response

### Runbook Template

```markdown
# Runbook: High Error Rate

## Alert
Name: HighErrorRate
Severity: Critical

## Impact
Users experiencing failed requests, potential service degradation

## Detection
Error rate > 5% for 5 minutes

## Response Steps
1. Check Grafana dashboard for error patterns
2. Review recent deployments
3. Check application logs in Loki
4. Verify database connectivity
5. Check external service dependencies

## Rollback Procedure
```bash
kubectl rollout undo deployment/funkygibbon-api
```

## Escalation
- First 15 min: On-call engineer
- After 30 min: Team lead
- After 1 hour: Engineering manager
```

## Continuous Improvement

### Weekly Reviews
- Review alerts fired
- Analyze false positives
- Update thresholds
- Document learnings

### Monthly Reviews
- SLO performance
- Cost analysis
- Performance trends
- Capacity planning

### Quarterly Reviews
- Architecture review
- Tool evaluation
- Process improvements
- Team training
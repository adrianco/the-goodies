# Development Plans

This directory contains planning and development documentation for The Goodies smart home system.

## Current Plans

### Requirements & Scope
- **[simplified-requirements.md](simplified-requirements.md)** - Current simplified scope (single house, SQLite, last-write-wins)
- **[funkygibbon-python-implementation.md](funkygibbon-python-implementation.md)** - Python backend implementation details
- **[inbetweenies-protocol.md](inbetweenies-protocol.md)** - Synchronization protocol specification
- **[blowing-off-client-implementation.md](blowing-off-client-implementation.md)** - Python test client implementation

### Development Steps
- **[funkygibbon-development-steps.md](funkygibbon-development-steps.md)** - Python backend development plan
- **[wildthing-development-steps.md](wildthing-development-steps.md)** - Swift package development plan
- **[wildthing-interface-design.md](wildthing-interface-design.md)** - Swift package interface specifications

### Project Management
- **[milestones.md](milestones.md)** - Project milestones and goals
- **[project-timeline.md](project-timeline.md)** - Development timeline (4 weeks instead of 12)
- **[weekly-deliverables.md](weekly-deliverables.md)** - Week-by-week deliverables
- **[risk-mitigation-plan.md](risk-mitigation-plan.md)** - Risk assessment and mitigation
- **[DOCUMENTATION_STATUS.md](DOCUMENTATION_STATUS.md)** - Source code documentation tracking

### Implementation & Deployment
- **[implementation-guide.md](implementation-guide.md)** - Overall implementation strategy
- **[quick-start-guide.md](quick-start-guide.md)** - Getting started quickly
- **[configuration-guide.md](configuration-guide.md)** - Configuration documentation
- **[deployment-plan.md](deployment-plan.md)** - Deployment strategy
- **[docker-deployment.md](docker-deployment.md)** - Docker containerization
- **[monitoring-setup.md](monitoring-setup.md)** - Monitoring and observability

### iOS Integration
- **[c11s-ios-house-integration-plan.md](c11s-ios-house-integration-plan.md)** - iOS app integration planning
- **[c11s-ios-house-pr-strategy.md](c11s-ios-house-pr-strategy.md)** - Pull request strategy
- **[c11s-ios-house-pr.md](c11s-ios-house-pr.md)** - iOS app integration PR details

## Archived Plans

The [archive](archive/) directory contains obsolete planning documents from when the project had enterprise-scale ambitions. These have been superseded by the simplified single-house approach.

## Current Status

- ✅ **FunkyGibbon (Python)**: Functional with API, models, repositories, and tests
- 🚧 **Blowing-Off (Python Client)**: In development - test client implementation
- 🚧 **Inbetweenies Protocol**: Specified - synchronization protocol
- 📋 **WildThing (Swift)**: Planned, interface designed
- 📋 **iOS Integration**: Ready to begin once WildThing is implemented
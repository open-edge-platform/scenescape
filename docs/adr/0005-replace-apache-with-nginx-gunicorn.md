# ADR 5: Replace Apache with Nginx + Gunicorn for Manager Service

- **Author(s)**: [Mikolaj Kasprzak](https://github.com/MikolajKasprzak)
- **Date**: 2025-10-21
- **Status**: Proposed

## Context

The SceneScape Manager service was originally hosted using Apache with mod_wsgi, which introduced several operational and security challenges:

### Key Problems:

1. **Security vulnerabilities**: Apache required root privileges for initialization, creating unnecessary attack surface
2. **Complex configuration**: Multi-layered Apache configuration with mod_wsgi, SSL termination, and proxy rules was difficult to maintain
3. **Volume permission issues**: Dynamic UID/GID changes led to unreliable file system permissions
4. **Deployment complexity**: Monolithic container with Apache + Django made scaling and debugging difficult
5. **Resource overhead**: Apache's process model was heavier than needed for a Python web application

### Technical Debt:

- Complex initialization scripts (`scenescape-init`, `webserver-init`) with root privilege requirements
- Dynamic user/group ID management causing permission denied errors
- Mixed responsibilities in single container (web server + application server)
- Legacy configuration files and unused dependencies

The system needed a more secure, maintainable, and cloud-native architectu re aligned with modern containerization best practices.

## Decision

We will replace the Apache + mod_wsgi architecture with a **Nginx + Gunicorn** separation of concerns approach:

### New Architecture:

#### Docker Compose Deployment:

1. **Manager Container**:
   - Runs Gunicorn WSGI server as unprivileged user
   - Serves Django application on internal port 8000
   - Simplified entrypoint script without root privileges

2. **Nginx Container**:
   - Handles SSL/TLS termination (HTTPS on port 443)
   - Serves static files efficiently
   - Proxies dynamic requests to Gunicorn
   - Manages WebSocket proxy for MQTT broker
   - Runs as separate service for better isolation

#### Kubernetes Deployment:

1. **Sidecar Pattern**:
   - **Django Container**: Gunicorn WSGI server on port 8000
   - **Nginx Sidecar**: Static files and internal routing within Pod
   - **Broker**: Kubernetes ingress should be sufficient no need for sidecar
   - Shared volumes for static files and media between containers
   - Communication over localhost within Pod

2. **Kubernetes Ingress**:
   - Handles external traffic routing and SSL/TLS termination
   - Can manage certificate lifecycle with cert-manager
   - Routes HTTP/HTTPS traffic to nginx sidecar
   - Provides load balancing and high availability

3. **Volume Management**:
   - Init container sets proper permissions once at startup
   - Fixed UID/GID (1000:1000) eliminates dynamic user changes
   - Shared emptyDir volumes for static files within Pod

### Configuration Changes:

#### Docker Compose:

- Replace complex Apache config with simple nginx.conf
- Eliminate `webserver-init` and `scenescape-init` scripts
- Use single `entrypoint.sh` for Django initialization
- Add CSRF trusted origins for reverse proxy setup

#### Kubernetes:

- Helm chart with sidecar nginx configuration
- Kubernetes Ingress resource for external access
- ConfigMaps for nginx configuration
- Init containers for static file collection
- Service mesh ready architecture (if there is requirement for TLS in internal network)

## Alternatives Considered

### Option A: Nginx + Gunicorn with Kubernetes Sidecar (Selected)

- **Pros**: Industry standard, security best practices, clean separation, excellent performance, Kubernetes-native
- **Cons**: Requires container architecture changes, initial migration effort, slightly more complex Pod spec

### Option B: Pure Kubernetes Ingress (Considered)

- **Pros**: Fully cloud-native, managed SSL, automatic scaling
- **Cons**: Complex static file handling, limited WebSocket support, MQTT proxy challenges

### Option C: Use WhiteNoise

- **Pros**: Can be used on top of Option B, static files handled by Whitenoise, no need for nginx sidecar
- **Cons**: Manager code changes

## Consequences

### Positive

- **Enhanced Security**: No root privileges required in application container
- **Simplified Maintenance**: Clean separation of concerns
- **Improved Scalability**: Independent scaling of web server and application server
- **Reduced Attack Surface**: Minimal container with only necessary components
- **Easier Debugging**: Clear separation between infrastructure (nginx) and application (django)
- **Volume Reliability**: Fixed permissions eliminate dynamic UID/GID issues for manager and apache user
- **Kubernetes Native**: Sidecar pattern enables proper cloud-native deployment
- **TLS Management**: Kubernetes Ingress with cert-manager or different solution for automatic certificate lifecycle or we can stay with current approach

### Negative

- **Migration Effort**: Requires updating deployment scripts and documentation
- **Two Containers**: Slightly more complex docker-compose setup
- **Initial Setup**: Need to configure nginx proxy rules and SSL certificates
- **Compatibility**: May require CSRF and WebSocket configuration adjustments

## References

- [Nginx official documentation](https://nginx.org/en/docs/)
- [Gunicorn deployment guide](https://docs.gunicorn.org/en/stable/deploy.html)
- [Django production deployment best practices](https://docs.djangoproject.com/en/4.2/howto/deployment/)
- [Container security best practices](https://kubernetes.io/docs/concepts/security/overview/)
- [Kubernetes Sidecar pattern](https://kubernetes.io/docs/concepts/workloads/pods/)
- [Kubernetes Ingress controllers](https://kubernetes.io/docs/concepts/services-networking/ingress/)
- [Kubernetes Init Containers](https://kubernetes.io/docs/concepts/workloads/pods/init-containers/)

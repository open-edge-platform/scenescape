# Documentation Update Procedures

For guidance on WHEN to update documentation, see the "Documentation Requirements (Always-On)" section in `.github/copilot-instructions.md`.

This guide covers the HOW: where to make changes and what to update for each type of modification.

## Documentation Locations by Component

- **Service Overview**: `docs/user-guide/microservices/<service>/<service>.md` - Feature descriptions, API endpoints, usage examples
- **Build Instructions**: `docs/user-guide/microservices/<service>/get-started/build-from-source.md` - Build steps, Makefile targets, Docker commands
- **Service README**: `<service>/README.md` - Quick start and high-level overview (if exists)
- **API Specifications**: `docs/user-guide/microservices/<service>/**/_assets/*.yaml` or `api-reference.md` - API specs/references for REST APIs
- **Root Documentation**: `docs/user-guide/` - Cross-service documentation, architecture guides
- **Testing Guide**: `tests/README.md` and service-specific test docs (for example `mapping/tests/README.md`) - Test setup and execution instructions

## Documentation Update Checklist

When making changes, verify and update:

1. **Feature descriptions** in overview.md (list all options/variants)
2. **Build commands** in `build-from-source.md` (include new targets)
3. **API documentation** (if endpoints or parameters changed)
4. **Example code** (reflect new options/parameters)
5. **Configuration examples** (show new variables/options)
6. **Prerequisites** (new dependencies or system requirements)
7. **Testing instructions** (if test setup changed)

## Example Patterns

### For Model Selection Features (e.g., mapping service):

- List ALL available models/options in overview
- Show build command for EACH variant
- Update API examples to mention model selection
- Update health check/status responses with new model info

### For New Services:

1. Create `docs/user-guide/microservices/<service>/` directory structure
2. Write `<service>.md` with feature descriptions and API endpoints
3. Write `get-started/build-from-source.md` with build instructions
4. Create or update API references (`api-reference.md` and/or `_assets/*.yaml`) if applicable
5. Create tests/README.md with test execution instructions
6. Update root `docs/user-guide/` with cross-service documentation
7. Update main README.md if major functionality change

### For Configuration Changes:

1. Document all new environment variables in the service overview (`<service>.md`)
2. Provide example `.env` snippets
3. Update `build-from-source.md` with configuration instructions
4. List new configuration files or schema changes
5. Show examples of before/after configurations if behavior changed

### For API Changes:

1. Update OpenAPI/Swagger spec (`_assets/*.yaml`) or `api-reference.md`
2. Update service overview (`<service>.md`) with new endpoints/parameters
3. Update example code in `build-from-source.md`
4. Document deprecations or breaking changes
5. Provide migration guides if backward compatibility broken

## Service-Specific Documentation Examples

### Controller Service

- **Overview** (`docs/user-guide/microservices/controller/controller.md`): Scene management, object tracking, REST API
- **Build** (`docs/user-guide/microservices/controller/get-started/build-from-source.md`): Makefile targets, Docker commands
- **API Spec** (`docs/user-guide/microservices/controller/api-reference.md` and `_assets/scene-controller-api.yaml`): gRPC/REST endpoint definitions
- **Tests** (`controller/tests/README.md`): Unit, functional, integration test execution

### Manager Service

- **Overview** (`docs/user-guide/using-intel-scenescape/` and related guides): Web UI features, REST API, database schema
- **Build** (`docs/user-guide/get-started.md` and root build guides): Django setup, migrations, static files
- **API Spec** (`docs/user-guide/api-reference.md`): REST endpoint definitions
- **Tests** (`manager/tests/README.md`): UI tests, functional tests, API tests

### Autocalibration Service

- **Overview** (`docs/user-guide/microservices/auto-calibration/auto-calibration.md`): Calibration algorithms, input/output formats
- **Build** (`docs/user-guide/microservices/auto-calibration/get-started/build-from-source.md`): Build commands, dependencies
- **API Spec** (`docs/user-guide/microservices/auto-calibration/api-reference.md`): REST API for calibration requests

## Cross-Service Documentation

Root-level documentation in `docs/user-guide/`:

- **Architecture overview** - System design and component interactions
- **Getting Started** - Initial setup and quick start guide
- **Build Instructions** - Root Makefile targets, build system overview
- **Deployment** - Docker Compose, Kubernetes setup
- **Development Guide** - Local development workflow
- **Testing** - Test execution across all services
- **API Reference** - Complete API documentation index

Update root documentation when:

- Making changes that affect multiple services
- Updating build system or deployment procedures
- Adding new testing procedures
- Changing development workflow

# Documentation Requirements

**CRITICAL**: Documentation MUST be updated whenever code changes affect user-facing functionality, APIs, configuration, or workflows.

## When to Update Documentation

- Adding new features, services, models, or options
- Modifying APIs, endpoints, or request/response formats
- Changing build targets, Makefile commands, or deployment procedures
- Adding or removing configuration options or environment variables
- Updating dependencies or system requirements
- Changing default behaviors or conventions

## Documentation Locations by Component

- **Service Overview**: `<service>/docs/user-guide/overview.md` - Feature descriptions, API endpoints, usage examples
- **Build Instructions**: `<service>/docs/user-guide/How-to-build-source.md` - Build steps, Makefile targets, Docker commands
- **Service README**: `<service>/README.md` - Quick start and high-level overview (if exists)
- **API Specifications**: `<service>/docs/*.yaml` - OpenAPI/Swagger specs for REST APIs
- **Root Documentation**: `docs/user-guide/` - Cross-service documentation, architecture guides
- **Testing Guide**: `<service>/tests/README.md` - Test setup and execution instructions

## Documentation Update Checklist

When making changes, verify and update:

1. **Feature descriptions** in overview.md (list all options/variants)
2. **Build commands** in How-to-build-source.md (include new targets)
3. **API documentation** (if endpoints or parameters changed)
4. **Example code** (reflect new options/parameters)
5. **Configuration examples** (show new variables/options)
6. **Prerequisites** (new dependencies or system requirements)
7. **Testing instructions** (if test setup changed)

## Example Patterns

For model selection features (like mapping service):

- List ALL available models/options in overview
- Show build command for EACH variant
- Update API examples to mention model selection
- Update health check/status responses with new model info

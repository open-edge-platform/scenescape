# Scenescape

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/open-edge-platform/scenescape/badge)](https://scorecard.dev/viewer/?uri=github.com/open-edge-platform/scenescape)

Scenescape makes writing applications based on sensor data faster, easier and better by reaching beyond vision-based AI to realize spatial awareness through contextualization of multimodal sensor data in a common reference frame. It is a reference architecture which provides a collection of microservices, tools and supporting containers to quickly move from single sensor analytics to a multimodal aggregated scene view.

## Documentation

- **Overview**
  - [Overview and Architecture](docs/user-guide/index.md): A high-level introduction.

- **Getting Started**
  - [Get Started](docs/user-guide/get-started.md): Step-by-step guide to getting started with the Scenescape.

- **API Reference**
  - [API Reference](docs/user-guide/api-reference.md): Comprehensive OpenAPI (Swagger) documentation for the Scenescape REST API, including endpoints, schemas, and usage examples.

## Community

- To report a bug, file a documentation issue, or submit a feature request, please open a [GitHub issue](https://github.com/open-edge-platform/scenescape/issues).

## Testing

All instructions and requirements for testing Scenescape can be found in [Testing Readme](tests/README.md).

## Contributing

We welcome contributions! Check out our [Contributing Guide](./CONTRIBUTING.md) to get started.

## License

Scenescape repository is licensed under [APACHE 2.0 LICENSE](./LICENSES/Apache-2.0.txt).

## Disclaimers

Depending on your deployment, Scenescape may utilize FFmpeg and/or GStreamer.

Scenescape provides microservices and a reference configuration intended to demonstrate integration patterns and platform capabilities. It is the responsibility of the developer or system integrator to harden production deployments, including secure service-to-service communication, authentication and authorization controls, secrets and certificate management, and appropriate observability measures (for example logging, metrics, tracing, and alerting) based on the target environment and risk profile.

FFmpeg is an open source project licensed under LGPL and GPL. See [https://www.ffmpeg.org/legal.html](https://www.ffmpeg.org/legal.html). You are solely responsible for determining if your use of FFmpeg requires any additional licenses. Intel is not responsible for obtaining any such licenses, nor liable for any licensing fees due, in connection with your use of FFmpeg.

GStreamer is an open source framework licensed under LGPL. See [https://gstreamer.freedesktop.org/documentation/frequently-asked-questions/licensing.html](https://gstreamer.freedesktop.org/documentation/frequently-asked-questions/licensing.html). You are solely responsible for determining if your use of GStreamer requires any additional licenses. Intel is not responsible for obtaining any such licenses, nor liable for any licensing fees due, in connection with your use of GStreamer.

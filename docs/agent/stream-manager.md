# Slide 1: Stream Manager

Value Proposition:
Stream Manager (SM) provides camera/video discovery, management, storage, and streaming capabilities fully integrated into the OEP ecosystem

Business Objectives:
- This service will act as a central OEP video ingestion and management hub with well-documented REST APIs
- Enabling downstream AI analytics services to access live and recorded streams
- Make it easy and fun to setup cameras and experiment with OEP

How we get there:
- Leverage our own work done with ViPPET, SceneScape, EIS, DLSPS
- Learn from competitors: NVIDIA VIOS
- Work with Milestone & Genitec

# Slide 2: Problem

In a nutshell:
- Lack of central OEP video ingestion and management service enabling downstream AI analytics services to access live and recorded streams
- No OEP solution to discover and setup cameras in an easy way
- No equivalent to NVIDIA VIOS (previously known as VST) – used in VSS Blueprint (link) and Jetson Platform Services (link)

# Slide 3: Proposal

Key design decisions
- Develop light MS with runtime REST control interface
- API supporting ViPPET, SceneScape, VSS requirements
- Modern SW Stack (FastAPI)

Timeline & Effort Needed
- 2026.2:
  - Reuse of ViPPET’s ONVIF Discovery MS a foundation for Stream Manager MS (1MW)
  - API v.1.0 implementation (6MW)
  - ViPPET team: sensors API
  - SceneScape team: livestreams/replays API
  - VSS team: records API
  - ViPPET adopts Stream Manager MS (1MW)
- 2026.3:
  - SceneScape adopts Stream Manager MS
  - VSS adopts Stream Manager MS
  - Reusable reference Stream Manager UI implementation

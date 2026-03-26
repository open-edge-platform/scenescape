# How to Build Scene Controller from Source

## Prerequisites

- The hardware platform must be at least a 10th Generation Intel® Core™ i5 Processor or Intel® Xeon® Scalable processor, with at least 8+GB of RAM and 64+GB of storage.

## Steps to build

- **Clone the Repository**:
  Clone the repository.

  ```bash
  git clone https://github.com/open-edge-platform/scenescape.git
  ```

  **Expected output:** Repository is cloned and a `scenescape/` directory is created.

> **Note:** Adjust the repo link appropriately in case of forked repo.

- **Navigate to the Directory**:

  ```bash
  cd scenescape
  ```

  **Expected output:** Shell prompt changes to the SceneScape repository root.

- **Build controller**:

  ```bash
  make controller
  ```

  **Expected output:** Controller image build completes successfully.

## Next Steps

Proceed to [Run the service using Docker Compose](../get-started.md#run-the-service-using-docker).

# Create and Manage a Scene Hierarchy in Scenescape

A hierarchy of scenes can be created using a parent-child relationship, enabling scene analytics from multiple scenes — whether on the [same system](#steps-to-add-a-local-child-scene) or [different systems in same network](#steps-to-add-a-remote-child-scene) running Scenescape — to be visualized within a single parent scene. This hierarchy is not limited to a single level of relationship; it can be scaled upwards, allowing for multi-level parent-child configurations. By subscribing to the parent scene's events, you can observe the base analytics (such as regions of interest, tripwires, and sensors) of the parent scene, along with the transformed base analytics of all its child scenes, directly within the parent scene.

> **Same host, multiple Scene Controllers:** Local children share one controller.
> To run several controllers on one machine and link them as remote children
> (including sharing or splitting a ReID database), see
> [Deploy Multiple Controllers on One Host](./deploy-multi-controller-on-one-host.md).

This guide provides step-by-step instructions to add local and remote child scenes, configure connections, and manage object tracking and update fidelity in a scene hierarchy. By completing this guide, you will:

- Add and validate child scene links (local and remote).
- Configure secure communication between systems.
- Tune retrack and temporal fidelity options.

This task is essential for managing distributed scenes in Scenescape deployments.

## Prerequisites

- **Installed Dependencies**: Scenescape deployed on both systems.
- **Network Access**: Verify systems can resolve each other's IP/hostname.
- **Permissions**: Ensure access to modify `docker-compose.yml` and certificates.

---

## Steps to Add a Local Child Scene

1. **Launch the Scenescape UI and Log In**.
2. Navigate to the parent scene.
3. Click the **Children** tab under the scene map.
4. Click **+ Link Child Scene**.
5. Set **Child Type** to `Local`.
6. Select the scene to be added from the dropdown list.
7. Enter transform type and values.
8. Click **Add Child Scene**.

**Expected Result**: The child scene appears in the parent scene view.

![Local Child Form](../../_assets/ui/local_child_link_form.png "local child scene form")

_Figure 1: Creating new local child scene link._

![Local Child Saved](../../_assets/ui/local_child_saved.png "local child scene saved")

_Figure 2: Local Child scene on scene detail page._

---

## Steps to Add a Remote Child Scene

### 1. Configure NTP for Synchronization

**On Parent System**:

- Edit `docker-compose.yml` to uncomment NTP server port.

![Parent NTP Config](../../_assets/parent_ntp_conf.png "parent ntp config")

**On Child System**:

- Edit `docker-compose.yml` to uncomment MQTT broker port.

![Child MQTT broker Config](../../_assets/child_broker_conf.png "child mqtt broker config")

- Disable NTP server service in `docker-compose.yml`.
- Replace `ntpserv` with parent IP in dependent services.

![Child Config 1](../../_assets/child_ntp_conf_1.png "child ntp config 1")

_Figure 3: ntpserver config for scene controller service in `docker-compose.yml`._

![Child Config 2](../../_assets/child_ntp_conf_2.png "child ntp config 2")

_Figure 4: comment ntpserver for DL Streamer Pipeline Server in `docker-compose.yml`._

![Child Config 3](../../_assets/child_ntp_conf_3.png "child ntp config 3")

_Figure 5: ntpserver config for DL Streamer Pipeline in `pipeline-config.json`._

> **Note**: Use [sample_data/docker-compose-dl-streamer-example.yml](https://github.com/open-edge-platform/scenescape/blob/release-2026.1.0/sample_data/docker-compose-dl-streamer-example.yml) if `docker-compose.yml` does not exist.

### 2. Set Up Secure Communication

> **Note:** For details on available Docker Compose profiles, see [Docker Compose Profiles](../../get-started.md#docker-compose-profiles).

**On Parent system**:

```bash
./deploy.sh
docker compose --profile controller down --remove-orphans
rm manager/secrets/ca/* manager/secrets/certs/*
make -C tools/certificates/ deploy-certificates CERTPASS=<random-string>
```

**On Child system**:

> **Note:** Ensure that there are no scenes with the same UUID present on both the parent and child systems.

```bash
./deploy.sh
docker compose --profile controller down --remove-orphans
rm manager/secrets/ca/* manager/secrets/certs/*
# Copy parent secrets:
scp parent:/path-to-scenescape-repo/manager/secrets/ca/scenescape-ca.key ./manager/secrets/ca/
scp parent:/path-to-scenescape-repo/manager/secrets/certs/scenescape-ca.pem ./manager/secrets/certs/
# Use the same CERTPASS from parent
 make -C tools/certificates/ deploy-certificates IP_SAN=<child_ip> CERTPASS=<random-string-used-in-parent>
```

Then restart Scenescape:

```bash
./deploy.sh
```

### 3. Link Remote Child

1. Open the child system's Scenescape UI and copy the MQTT credentials.
2. Open the parent system's Scenescape UI.
3. Go to the **Children** tab in parent scene.
4. Click **+ Link Child Scene**.
5. Select `Remote` as child type and enter:
   - Child Name
   - Hostname or IP
   - MQTT Username/Password
   - Transform type/values
6. Click **Add Child Scene**.

![Remote Child Form](../../_assets/ui/remote_child_link_form.png "remote child scene form")

_Figure 5: Creating new remote child scene link._

![Remote Child Saved](../../_assets/ui/remote_child_saved.png "remote child scene saved")

_Figure 6: Remote child scene on scene detail page._

**Expected Result**: Remote child is listed with green/red status icon.

> **Note:** Scene names must be unique across parent and child systems.

---

## Retrack Objects in Parent Scene

- Open the child link config in the UI.
- Toggle the **Retrack** option:
  - **Disabled**: Treat detections as already tracked.
  - **Enabled**: Feed detections into the parent tracker.

![Retrack Toggle](../../_assets/ui/child-link-retrack.png "retrack toggle")

_Figure 7: Toggle to re-track moving objects from child scene._

---

## Set Temporal Fidelity of Scene Updates

- Navigate to the scene configuration.
- Configure the following:
  - `Regulate Rate (Hz)`: Limit updates to internal UI.
  - `Max External Update Rate (Hz)`: Limit updates to parent/consuming systems.

![Temporal Fidelity](../../_assets/ui/temporal-fidelity.png "temporal fidelity")

_Figure 8: Set Regulate and External Update rate in scene config._

---

## Re-identification Support in Hierarchy

**Hierarchy ReID rules (short):**

- Prefer local children on one controller when practical.
- **Unrelated** controllers may **share** one ReID DB or run **separate**
  instances.
- Under one parent, do **not** give different children (or child vs parent)
  **different** ReID databases if you expect one identity space.
- **Parent-owned cameras:** parent enrolls. **Child-forwarded** embeddings
  (`retrack=True`): parent queries with provenance; sole-enrolls on
  query-no-match when the child has no ReID; after rematch, enhances that
  UUID's embedding cluster with further vetted forwarded vectors.
- When using ReID in a hierarchy and you want one identity space across
  children and parent cameras, **enable Retrack**. With Retrack **off**, the
  parent keeps child UUIDs and strips reid—no fusion—so child enrollments and
  parent-camera enrollments can land in the DB under **different** UUIDs.
- **Parent ReID + children without ReID** (embedding passthrough) is
  [supported](./deploy-multi-controller-on-one-host.md#hierarchy-supported-reid-layouts):
  parent enrolls child-only crops on no-match and rematches siblings to that UUID.
- When children need local rematch, put parent and those children on the
  **same** shared backend.

Scenes that are **not** in a parent/child relationship:
[share or separate ReID](./deploy-multi-controller-on-one-host.md#unrelated-scenes-share-a-db-or-use-separate-instances).

How a parent scene handles identity depends on the **Retrack** setting of each child link:

- **Retrack disabled**: the child's identities are taken as final. The parent
  forwards child objects with the UUIDs the child assigned, strips forwarded
  reid, and does not re-identify them. **Do not use this with ReID** if you
  expect parent cameras and children to share one durable UUID—enable Retrack
  instead ([details](./deploy-multi-controller-on-one-host.md#retrack-when-using-reid-in-a-hierarchy)).
- **Retrack enabled**: the parent runs its own tracker, queries its ReID
  database with forwarded embeddings (when present and provenance-vetted), and
  enrolls those crops only on query-no-match. Durable rematch to enrolled IDs
  is reliable when tracks rematch **sequentially**; two live parent tracks will
  not both adopt the same database UUID
  ([ADR 0015](../../../adr/0015-hierarchy-reid-provenance.md#how-should-two-live-parent-tracks-share-one-reid-database-identity)).
  Geometric tracker merge can still collapse detections that project to the same place.

Embeddings a child forwards carry the id of the scene and camera that produced them, along with
confirmation that the crop passed the `minimum_bbox_area` quality gate where it was measured. A
parent uses those embeddings to match identities, but only the scene that owns the source camera
(and has ReID enrollment enabled) contributes them to the re-identification database.

> Refer to [Re-identification Guide](../../other-topics/how-to-enable-reidentification.md) for more details.
> Full matrix:
> [ReID Across Controllers](./deploy-multi-controller-on-one-host.md#reid-across-controllers-what-is-supported).

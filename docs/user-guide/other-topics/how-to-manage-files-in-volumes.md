# How to Manage Files in Volumes

## Manage files in Docker volumes

> **Note**: In the commands below the default Docker Compose project name `scenescape` is used. Adjust it accordingly if Intel® SceneScape is installed with another project name.

### Identify the volume

The volume names can be identified by looking for keywords in their names. Before running the commands below, set the environment variable in the shell:

- `VOL_KEYWORD=models` for the Models Volume.
- `VOL_KEYWORD=sample-data` for the Sample-Data Volume.

**Verify the Docker Volume exists:**

```bash
# as a prerequisite, set the VOL_KEYWORD variable accordingly
VOLUME=$(docker volume ls --format "{{.Name}}" | grep "scenescape_vol-$VOL_KEYWORD" | head -n 1)
if [ -z "$VOLUME" ]; then
    echo "Error: Volume with keyword '$VOL_KEYWORD' not found"
    exit 1
fi
echo "Volume name: $VOLUME"
```

### Access the Docker volume

#### List the Docker volume contents

```bash
docker run --rm -v "$VOLUME:/volume" alpine ls -la /volume
```

#### Execute a single arbitrary command accessing Docker volume

```bash
docker run --rm -v "$VOLUME:/volume" alpine <command> <arguments...>
```

For example, to find JSON files within the volume:

```bash
docker run --rm -v "$VOLUME:/volume" alpine find /volume -name '*.json' -print
```

#### Execute shell to access the Docker volume

```bash
docker run --rm -it -v "$VOLUME:/volume" alpine sh -c "cd /volume && sh"
```

#### Copy files to the Docker volume

```bash
docker run --rm -v "/path/to/local/directory:/source" -v "$VOLUME:/volume" alpine cp /source/local.file /volume/destination_path/destination.file
```

After the copy operation completes, verify the file transfer by listing the volume contents to check the files.

## Manage files in Kubernetes volumes

> **Note**: In the commands below the default namespace `scenescape` is used. Adjust it accordingly if the Intel® SceneScape chart is installed in another namespace.

> **Prerequisites**: The commands in this section require `jq` for JSON processing. Install it using your system package manager: `apt install jq`, `yum install jq`, or `brew install jq`.

### Identify the volume name

The volume names can be identified by looking for keywords in their names. Before running the commands below, set the environment variable in the shell:

- `VOL_KEYWORD=models` for the Models Volume.
- `VOL_KEYWORD=sample-data` for the Sample-Data Volume.

**Find the Persistent Volume Claim name (PVC):**

```bash
# as a prerequisite, set the VOL_KEYWORD variable accordingly
VOLUME=$(kubectl get pvc -n scenescape | grep $VOL_KEYWORD | head -n 1 | awk '{ print $1 }')
echo "Volume name: $VOLUME"
```

### Identify the mount path

**Find the Pod that has the volume mounted**

First, list all pods that mount the volume:

```bash
echo "Pods that mount volume $VOLUME:"
kubectl get pods -n scenescape -o wide --no-headers | awk '{print $1}' | while read pod; do
    if kubectl get pod $pod -n scenescape -o jsonpath='{.spec.volumes[*].persistentVolumeClaim.claimName}' | grep -q "$VOLUME"; then
        # Check if the volume mount name contains the keyword
        READONLY=$(kubectl get pod $pod -n scenescape -o json | jq -r --arg keyword "$VOL_KEYWORD" '.spec.containers[].volumeMounts[] | select(.name | contains($keyword)) | .readOnly // false')
        MOUNT_NAME=$(kubectl get pod $pod -n scenescape -o json | jq -r --arg keyword "$VOL_KEYWORD" '.spec.containers[].volumeMounts[] | select(.name | contains($keyword)) | .name')
        echo "  $pod (mount: $MOUNT_NAME, readOnly: $READONLY)"
    fi
done
```

**Select a pod with proper access:**

Choose a pod from the list above with proper access to the volume and copy-paste its name into the command below. For write access, choose a pod where `readOnly` is `false` or not set at all.

```bash
# Replace with the pod name that has readOnly: false
POD_NAME="<pod-name-with-write-access>"
echo "Pod name: $POD_NAME"
```

> **Tip**: For the Models Volume, web-app pods typically have write access. For the Sample-Data Volume, video pipeline pods usually have write access.

**Identify the volume mount name:**

Find the volume mount name by querying the pod specification for the volume that references our PVC:

```bash
VOLUME_MOUNT=$(kubectl get pod $POD_NAME -n scenescape -o json | jq -r '.spec.volumes[] | select(.persistentVolumeClaim.claimName=="'$VOLUME'") | .name')
echo "Volume mount name: $VOLUME_MOUNT"
```

**Identify the mount path of the volume:**

```bash
MOUNT_PATH=$(kubectl get pod $POD_NAME -n scenescape -o json | jq -r '.spec.containers[].volumeMounts[] | select(.name=="'$VOLUME_MOUNT'") | .mountPath')
echo "Mount path: $MOUNT_PATH"
```

### Access the Kubernetes volume

#### List the Kubernetes volume contents

```bash
kubectl exec -n scenescape $POD_NAME -- ls -la $MOUNT_PATH
```

#### Execute a single arbitrary command accessing Kubernetes volume

```bash
kubectl exec -n scenescape $POD_NAME -- <command> <arguments...>
```

For example, to find JSON files within the volume:

```bash
kubectl exec -n scenescape $POD_NAME -- find $MOUNT_PATH -name '*.json' -print
```

#### Execute shell to access the Kubernetes volume

```bash
kubectl exec -it -n scenescape $POD_NAME -- /bin/sh -c "cd $MOUNT_PATH && /bin/sh"
```

#### Copy files to the Kubernetes volume

```bash
kubectl cp /path/to/local.file scenescape/$POD_NAME:$MOUNT_PATH/destination_path/destination.file
```

After the copy operation completes, verify the file transfer by listing the volume contents or executing a shell command to check the files.

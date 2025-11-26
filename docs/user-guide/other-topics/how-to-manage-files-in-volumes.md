# How to manage files in volumes

## Manage files in Docker volumes

### Identify the volume


### Access the volume

#### List the volume contents

#### Execute shell to access the volume

#### Copy files to the volume

## Manage files in Kubernetes volumes

> **Note**: In the commands below the default namespace `scenescape` is used. Adjust it accordingly if the SceneScape chart is installed in another namespace.

> **Prerequisites**: The commands in this section require `jq` to be installed for JSON processing. Install it using your system package manager: `apt install jq`, `yum install jq`, or `brew install jq`.

### Identify the volume name

The volume names can be identified by looking for keywords in their names. Before running the commands below set the environment variable in the shell:
- `VOL_KEYWORD=models` for models volume.
- `VOL_KEYWORD=sample-data` for sample-data volume.

**Find the Persistent Volume Claim name (PVC):**

```bash
# as a prerequisite set VOL_KEYWORD variable accordingly
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
        # Check if the volume mount is read-only
        READONLY=$(kubectl get pod $pod -n scenescape -o json | jq -r '.spec.containers[].volumeMounts[] | select(.name=="'$VOL_KEYWORD'-storage") | .readOnly // false')
        echo "  $pod (readOnly: $READONLY)"
    fi
done
```

**Select a pod with write access:**

Choose a pod from the list above where `readOnly` is `false` or not set at all, then set it manually:

```bash
# Replace with the pod name that has readOnly: false
POD_NAME="<pod-name-with-write-access>"
echo "Pod name: $POD_NAME"
```

> **Tip**: For models volume, web-app pods typically have write access. For sample-data volume, video pipeline pods usually have write access.

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

### Access the volume

#### List the volume contents

```bash
kubectl exec -n scenescape $POD_NAME -- ls -la $MOUNT_PATH
```

#### Execute shell to access the volume

```bash
kubectl exec -it -n scenescape $POD_NAME -- /bin/sh -c "cd $MOUNT_PATH && /bin/sh"
```

#### Copy files to the volume

**Copy the local file to the volume:**

```bash
kubectl cp /path/to/local.file scenescape/$POD_NAME:$MOUNT_PATH/destination_path/destination.file
```

**Verify:** List the volume contents or execute shell to verify the contents.

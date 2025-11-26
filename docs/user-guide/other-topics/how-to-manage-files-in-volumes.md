# How to manage files in volumes

## Manage files in Docker volumes

### Identify the volume


### Access the volume

#### List the volume contents

#### Execute shell to access the volume

#### Copy files to the volume

## Manage files in Kubernetes volumes

> **Note**: In the commands below the default namespace `scenescape` is used. Adjust it accordingly if the SceneScape chart is installed in another namespace.

> **Prerequisites**: The commands in this section require `jq` for JSON processing. Install it using your system package manager: `apt install jq`, `yum install jq`, or `brew install jq`.

### Identify the volume name

The volume names can be identified by looking for keywords in their names. Before running the commands below, set the environment variable in the shell:
- `VOL_KEYWORD=models` for the models volume.
- `VOL_KEYWORD=sample-data` for the sample-data volume.

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

> **Tip**: For the models volume, web-app pods typically have write access. For the sample-data volume, video pipeline pods usually have write access.

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

#### Execute a single arbitrary command

```bash
kubectl exec -n scenescape $POD_NAME -- <command> <arguments...>
```

For example, to find JSON files within the volume:

```bash
kubectl exec -n scenescape $POD_NAME -- find $MOUNT_PATH -name '*.json' -print
```

#### Execute shell to access the volume

```bash
kubectl exec -it -n scenescape $POD_NAME -- /bin/sh -c "cd $MOUNT_PATH && /bin/sh"
```

#### Copy files to the volume

```bash
kubectl cp /path/to/local.file scenescape/$POD_NAME:$MOUNT_PATH/destination_path/destination.file
```

After the copy operation completes, verify the file transfer by listing the volume contents or executing a shell command to check the files.

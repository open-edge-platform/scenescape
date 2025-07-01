// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

import * as THREE from '/static/assets/three.module.js';
import thingTransformControls from '/static/js/thing/controls/thingtransformcontrols.js';
import validateInputControls from '/static/js/thing/controls/validateinputcontrols.js';
import RESTClient from '/static/js/restclient.js';
import {
    REST_URL,
    SUCCESS
} from '/static/js/constants.js';

const DEFAULT_FLOOR_WIDTH = 1280;
const DEFAULT_FLOOR_HEIGHT = 720;
const DEFAULT_PPM = 100;
export default class Scene {
    constructor(sceneID, scene, parentFolder, perspectiveCamera, orthographicCamera, renderer, toast, orbitControls, axesHelper, isStaff) {
        let authToken = `Token ${document.getElementById("auth-token").value}`;
        this.restclient = new RESTClient(REST_URL, authToken);

        this.sceneID = sceneID;
        this.scene = scene;
        this.sceneMesh = null
        this.parentFolder = parentFolder;
        this.renderer = renderer;
        this.orbitControls = orbitControls;
        this.perspectiveCamera = perspectiveCamera;
        this.orthographicCamera = orthographicCamera;
        this.toast = toast;
        this.axesHelper = axesHelper;
        this.isStaff = isStaff;
        this.isParent = false;
        Object.assign(this, thingTransformControls);
        Object.assign(this, validateInputControls);
    }

    get transformObject() {
        return this.sceneMesh;
    }

    loadChildAnalytics(sceneThingManagers, thing) {
        const key = thing.concat('s');
        if (this.children) {
            for (const child of this.children) {
                if (key in child) {
                    for (const analytic of child[key]) {
                        const analyticsParams = sceneThingManagers.things[thing];
                        delete analytic.uid;
                        analyticsParams.obj.add(analytic);
                        analyticsParams.obj.update(0, analyticsParams);
                    }
                }
            }
        }
    }

    async loadMap(gltfLoader, loadThings, sceneBoundingBox) {
        let response = await this.restclient.getScene(this.sceneID);
        if (response.statusCode === SUCCESS) {
            this.name = response.content.name;
            this.pixelsPerMeter = response.content.scale;
            let mapis3d = response.content.map ? response.content.map.split('.').pop() === 'glb' : false;
            if (mapis3d) {
                this.load3DMap(gltfLoader, response.content, loadThings, sceneBoundingBox);
            } else {
                this.load2DMap(response.content, loadThings, sceneBoundingBox);
            }
            if ('children' in response.content) {
                this.isParent = true;
                this.children = response.content.children;
            }
        }
    }

    computePerspectiveCameraPose(floorWidth, floorHeight) {
        const center = { x: floorWidth / 2, y: floorHeight / 2 };
        let cameraZ = floorHeight / (2 * Math.tan(THREE.MathUtils.degToRad(this.perspectiveCamera.fov / 2)));
        return { cameraZ, center };
    }

    load3DMap(gltfLoader, sceneDetails, loadThings, sceneBoundingBox) {
        document.getElementById('loader-progress-wrapper').style.display = 'flex';
        let progressWrapper = document.getElementById('loader-progress-wrapper');
        let progressBar = progressWrapper.querySelector('.progress-bar');
        let currentProgressClass = 'width0';

        gltfLoader.load(
            sceneDetails.map,
            // called when the resource is loaded
            (gltf) => {
                this.sceneMesh = gltf.scene;
                // Position the scene 3D asset based on its configuration
                const settings = {
                    'rotation': {
                        'x': sceneDetails.mesh_rotation[0],
                        'y': sceneDetails.mesh_rotation[1],
                        'z': sceneDetails.mesh_rotation[2]
                    },
                    'position': {
                        'x': sceneDetails.mesh_translation[0],
                        'y': sceneDetails.mesh_translation[1],
                        'z': sceneDetails.mesh_translation[2]
                    },
                    'scale': {
                        'x': sceneDetails.mesh_scale[0],
                        'y': sceneDetails.mesh_scale[1],
                        'z': sceneDetails.mesh_scale[2]
                    }
                };

                for (const setting in settings) {
                    for (const axis in settings[setting]) {
                        if (settings[setting][axis] != null && settings[setting][axis] !== '') {
                            if (setting === 'rotation') this.sceneMesh[setting][axis] = THREE.MathUtils.degToRad(settings[setting][axis]);
                            else this.sceneMesh[setting][axis] = settings[setting][axis];
                        }
                    }
                }

                this.sceneMesh.name = '3d_scene';
                this.sceneMesh.castShadow = true;
                this.scene.add(this.sceneMesh);
                this.addControlPanel(true);
                this.addDragControls(this.perspectiveCamera, this.orbitControls);
                sceneBoundingBox.setFromObject(this.sceneMesh);
                const size = new THREE.Vector3();
                sceneBoundingBox.getSize(size);

                let floorWidth = size.x;
                let floorHeight = size.z;
                var { cameraZ, center } = this.computePerspectiveCameraPose(floorWidth, floorHeight);

                this.initializeScene(cameraZ, center, floorHeight, floorWidth);

                loadThings();

                document.getElementById('loader-progress-wrapper').style.display = 'none';
            },
            // called while loading is progressing
            (xhr) => {
                let percentBy5 = parseInt(xhr.loaded / xhr.total * 20) * 5;
                let percent = parseInt(xhr.loaded / xhr.total * 100);

                progressBar.classList.remove(currentProgressClass);
                currentProgressClass = 'width' + percentBy5;
                progressBar.classList.add(currentProgressClass);
                progressBar.setAttribute('aria-valuenow', percent);
                progressBar.innerText = 'Scene: ' + percent + '%';
            },
            // called when loading has errors
            (error) => {
                console.log('Error loading glTF: ' + error);
            }
        );
    }

    load2DMap(sceneDetails, loadThings, sceneBoundingBox) {
        let loader = new THREE.TextureLoader();
        if (sceneDetails.map) {
            loader.load(sceneDetails.map, (tex) => {
                let floorWidth = tex.image.width / this.pixelsPerMeter;
                let floorHeight = tex.image.height / this.pixelsPerMeter;
                var { cameraZ, center } = this.computePerspectiveCameraPose(floorWidth, floorHeight);

                // Create the scene floor using a PlaneGeometry
                // The size in meters is based on the scale as defined by the user and the image size
                const floorGeometry = new THREE.PlaneGeometry(floorWidth, floorHeight);
                const floorMaterial = new THREE.MeshLambertMaterial({
                    map: tex,
                    opacity: 0.8,
                    transparent: true
                });

                const floor = new THREE.Mesh(floorGeometry, floorMaterial);
                floor.name = 'floor';

                // Set the origin to the bottom left corner of the scene
                floor.position.set(center.x, center.y, 0);
                sceneBoundingBox.setFromObject(floor);

                // Set the perspective camera position.z based on the scene size and camera FOV
                this.initializeScene(cameraZ, center, floorHeight, floorWidth);
                loadThings();
                this.addControlPanel();

                floor['visible'] = this.axesHelper['visible'] = this.initFloorPlaneVisible();
                this.scene.add(floor);
            });
        } else {
            let floorWidth = DEFAULT_FLOOR_WIDTH / (this.pixelsPerMeter != null ? this.pixelsPerMeter : DEFAULT_PPM);
            let floorHeight = DEFAULT_FLOOR_HEIGHT / (this.pixelsPerMeter != null ? this.pixelsPerMeter : DEFAULT_PPM);
            var { cameraZ, center } = this.computePerspectiveCameraPose(floorWidth, floorHeight);

            // Set the perspective camera position.z based on the scene size and camera FOV
            this.initializeScene(cameraZ, center, floorHeight, floorWidth);
            loadThings();
            this.addControlPanel();

            this.axesHelper['visible'] = this.initFloorPlaneVisible();
        }
    }

    initializeScene(cameraZ, center, floorHeight, floorWidth) {
        this.perspectiveCamera.position.set(center.x, center.y, cameraZ);

        // Calculate the delta between the canvas width and the floor width
        let delta = (floorHeight * this.perspectiveCamera.aspect - floorWidth) / 2;

        // Set up the orthographic camera to match the canvas size and centered on the floor
        this.orthographicCamera.left = -delta;
        this.orthographicCamera.right = floorHeight * this.perspectiveCamera.aspect - delta;
        this.orthographicCamera.top = floorHeight;
        this.orthographicCamera.bottom = 0;
        this.orthographicCamera.position.set(0, 0, cameraZ);
        this.orthographicCamera.updateProjectionMatrix();

        // Directional scene lighting
        // Check if a directional light already exists and update it, otherwise add a new one
        let directionalLight = this.scene.getObjectByName('directionalLight');
        if (!directionalLight) {
            directionalLight = new THREE.DirectionalLight(0xffffff, 0.6);
            directionalLight.name = 'directionalLight';
            this.scene.add(directionalLight);
        }
        // Set the light above the origin to provide reasonable shading
        directionalLight.position.set(-center.x, -center.y, this.perspectiveCamera.position.z * 2);

        // Center orbit controls on the scene
        this.orbitControls.target.set(center.x, center.y, 1);

        // Save this as the initial view
        this.orbitControls.saveState();
        // Initial reset (sometimes the scene loads rotated otherwise)
        this.orbitControls.reset();

        this.scene.add(directionalLight);
    }

    // Initialize the floor plane visibility
    initFloorPlaneVisible() {
        // Browser only stores string, JSON.parse restores boolean value
        let showFloor = JSON.parse(localStorage.getItem('showFloor'));
        let checkbox = document.getElementById('plane-view');

        // Check if showFloor is in local storage yet
        if (showFloor === null) {
            if (checkbox.checked) {
                localStorage.setItem('showFloor', true);
                showFloor = true;
            } else {
                localStorage.setItem('showFloor', false);
                showFloor = false;
            }
        } else {
            // Set checkbox to the value from local storage
            checkbox.checked = showFloor;
        }

        return showFloor;
    }

    addControlPanel(isMesh = false) {
        let panelSettings = {
            'name': this.name,
            'pixels per meter': this.pixelsPerMeter != null ? this.pixelsPerMeter : "",
        };

        this.controlsFolder = this.parentFolder.addFolder('Scene Settings');
        let control = this.controlsFolder.add(panelSettings, 'name').onChange((function (value) {
            this.name = value;
            this.validateField('name', () => { return this.name === ''; });
        }).bind(this));

        control = this.controlsFolder.add(panelSettings, 'pixels per meter').onChange((function (value) {
            this.pixelsPerMeter = value;
            this.validateField('pixels per meter', () => { return this.pixelsPerMeter === ''; });
        }).bind(this));

        if (isMesh) {
            this.addPoseControls(panelSettings);
            this.controlsFolder.$title.addEventListener('click', ((event) => {
                this.toggleTransformControl();
            }).bind(this));
        }

        if (this.isStaff === null) {
            for (const field of Object.keys(panelSettings)) {
                this.executeOnControl(field, (control) => { control[0].domElement.classList.add('disabled') });
            }
        } else {
            panelSettings = Object.assign(panelSettings, { 'save': (function () { this.saveSettings() }).bind(this) });
            control = this.controlsFolder.add(panelSettings, 'save');
            this.executeOnControl('save', (control) => control[0].domElement.classList.add('disabled'));
        }

        this.controlsFolder.close();
    }

    updateSaveButton() {
        this.executeOnControl('save', (control) => control[0].domElement.classList.remove('disabled'));
    }

    async saveSettings() {
        let sceneData = {
            'scene': this.sceneID,
            'name': this.name,
            'scale': this.pixelsPerMeter,
        };

        if (this.transformObject !== null) {
            sceneData = Object.assign({}, sceneData, {
                'mesh_translation': [...this.transformObject.position],
                'mesh_rotation': [
                    this.transformObject.rotation.x,
                    this.transformObject.rotation.y,
                    this.transformObject.rotation.z
                ].map(function (item) {
                    return THREE.MathUtils.radToDeg(item);
                }),
            });
        }

        this.updateScene(sceneData);
        this.executeOnControl('save', (control) => control[0].domElement.classList.add('disabled'));
    }

    async updateScene(sceneData) {
        let updateResponse = await this.restclient.updateScene(this.sceneID, sceneData, { "timeout": 10000 });
        if (updateResponse.statusCode === SUCCESS) {
            this.toast.showToast('Scene mesh settings have been updated!', 'success');
            this.updateSceneObjects();
        } else {
            console.log(updateResponse.errors);
            this.toast.showToast('Something went wrong. Failed to update scene mesh settings. Please try again!', 'danger');
        }
    }

    updateSceneObjects() {
        // Update the scale and position of the scene objects based on the new pixels per meter value
        if (this.sceneMesh) {
            const size = new THREE.Vector3();
            const sceneBoundingBox = new THREE.Box3().setFromObject(this.sceneMesh);
            sceneBoundingBox.getSize(size);
            let floorWidth = size.x;
            let floorHeight = size.z;
            var { cameraZ, center } = this.computePerspectiveCameraPose(floorWidth, floorHeight);
            this.initializeScene(cameraZ, center, floorHeight, floorWidth);
        } else {
            // Handle 2D map case
            let floorWidth = DEFAULT_FLOOR_WIDTH / (this.pixelsPerMeter != null ? this.pixelsPerMeter : DEFAULT_PPM);
            let floorHeight = DEFAULT_FLOOR_HEIGHT / (this.pixelsPerMeter != null ? this.pixelsPerMeter : DEFAULT_PPM);
            var { cameraZ, center } = this.computePerspectiveCameraPose(floorWidth, floorHeight);
            this.initializeScene(cameraZ, center, floorHeight, floorWidth);
        }
    }
};

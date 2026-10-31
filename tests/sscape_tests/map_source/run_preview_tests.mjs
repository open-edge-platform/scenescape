// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import test from "node:test";

const source = await readFile(
  new URL(
    "../../../manager/src/manager/static/js/thing/scene.js",
    import.meta.url,
  ),
  "utf8",
);

const validationSource = await readFile(
  new URL(
    "../../../manager/src/manager/static/js/thing/controls/validateinputcontrols.js",
    import.meta.url,
  ),
  "utf8",
);

function element() {
  const classes = new Set();
  return {
    classList: {
      add: (value) => classes.add(value),
      remove: (value) => classes.delete(value),
      contains: (value) => classes.has(value),
      toggle(value, enabled) {
        if (enabled) classes.add(value);
        else classes.delete(value);
      },
    },
    setAttribute() {},
  };
}

function controller(property) {
  return {
    property,
    domElement: element(),
    $input: element(),
    $widget: element(),
    _disabled: false,
    buttonDisabled: false,
    disable(value = true) {
      if (value === this._disabled) return this;
      this._disabled = value;
      this.domElement.classList.toggle("disabled", value);
      this.buttonDisabled = value;
      return this;
    },
    onChange(callback) {
      this.change = callback;
      return this;
    },
  };
}

function assertDisabled(control, disabled) {
  assert.equal(control._disabled, disabled);
  assert.equal(control.domElement.classList.contains("disabled"), disabled);
  assert.equal(control.buttonDisabled, disabled);
}

function mesh() {
  const object = {
    visible: true,
    position: {
      set(...values) {
        this.values = values;
      },
    },
    rotation: {
      set(...values) {
        this.values = values;
      },
    },
    scale: {
      set(...values) {
        this.values = values;
      },
    },
    geometry: {
      disposed: 0,
      dispose() {
        this.disposed++;
      },
    },
    material: {
      disposed: 0,
      dispose() {
        this.disposed++;
      },
    },
    traverse(callback) {
      callback(this);
    },
    clone() {
      return { position: [0, 0, 0], rotation: { x: 0, y: 0, z: 0 } };
    },
  };
  object.material.map = {
    isTexture: true,
    disposed: 0,
    dispose() {
      this.disposed++;
    },
  };
  return object;
}

async function harness() {
  const loads = [];
  const writes = [];
  const notices = [];
  const controls = [
    "save",
    "name",
    "pixels per meter",
    "Update Cameras",
    "pos X",
    "rot X",
  ].map(controller);
  controls[0].disable(true);
  const progress = {
    style: {},
    querySelector: () => ({
      classList: { add() {}, remove() {} },
      setAttribute() {},
    }),
  };
  const context = vm.createContext({
    console,
    setTimeout() {},
    document: { getElementById: () => progress },
    window: { location: { reload() {} }, confirm: () => true },
  });
  class Loader {
    load(url, success, progress, failure) {
      loads.push({ url, success, progress, failure });
    }
  }
  const module = new vm.SourceTextModule(source, { context });
  await module.link(async (specifier) => {
    const exports = specifier.includes("three.module")
      ? {
          MathUtils: {
            degToRad: (value) => (value * Math.PI) / 180,
            radToDeg: (value) => (value * 180) / Math.PI,
          },
        }
      : specifier.includes("GLTFLoader")
        ? { GLTFLoader: Loader }
        : specifier.includes("constants")
          ? { REST_URL: "", SUCCESS: 200 }
          : { default: class {} };
    return new vm.SyntheticModule(
      Object.keys(exports),
      function () {
        for (const [name, value] of Object.entries(exports))
          this.setExport(name, value);
      },
      { context },
    );
  });
  await module.evaluate();
  const validation = new vm.SourceTextModule(validationSource, { context });
  await validation.link(() => {});
  await validation.evaluate();
  const active = mesh();
  const projection = mesh();
  const camera = {
    sceneCamera: {},
    mesh: projection,
    cameraCapture: { visible: true },
    projectFrame: true,
  };
  const sourceMaps = Object.fromEntries(
    ["active", "one", "two"].map((method, index) => [
      method,
      {
        method,
        file: `${method}.glb`,
        transform: {
          translation: [index, 2, 3],
          rotation: [0, 90, 0],
          scale: [2, 3, 4],
        },
      },
    ]),
  );
  const scene = Object.assign(
    Object.create(module.namespace.default.prototype),
    validation.namespace.default,
    {
      sceneID: "scene",
      sceneMesh: active,
      _defaultMethod: "active",
      _previewMethod: "active",
      _sourceMaps: sourceMaps,
      _mapSourceSettings: { "map source": "active" },
      _sourceMapLabels: { active: "active", one: "one", two: "two" },
      _mapSourceController: { updateDisplay() {} },
      scene: {
        add() {},
        remove() {},
        traverse(callback) {
          callback(camera);
        },
      },
      toast: {
        showToast(...args) {
          notices.push(args);
        },
      },
      controlsFolder: {
        controllersRecursive: () => controls,
        $title: element(),
      },
      transformControl: { enabled: true, attach() {}, detach() {} },
      getTransformControlObject3D: () => ({ visible: true }),
      setTransformControlVisibility() {},
      executeOnControl(property, callback) {
        callback(controls.filter((control) => control.property === property));
      },
      updateCamerasOnSave: true,
      async _applyMeshDeltaToCamerasAndSave() {
        writes.push("cameras");
      },
      async updateScene() {
        writes.push("scene");
      },
      restclient: {
        async activateSourceMap(...args) {
          writes.push(args);
          return { statusCode: 200 };
        },
      },
    },
  );
  return {
    scene,
    active,
    camera,
    projection,
    controls,
    loads,
    writes,
    notices,
    progress,
  };
}

async function sourceControlsHarness(methods, defaultMethod) {
  const state = await harness();
  const widgets = {};
  const folders = [];
  state.scene.restclient.getSourceMaps = async () => ({
    statusCode: 200,
    content: {
      maps: methods.map((method) => state.scene._sourceMaps[method]),
      default: defaultMethod,
    },
  });
  state.scene.controlsFolder.addFolder = (name) => {
    folders.push(name);
    return {
      add(settings, property, options) {
        const widget = {
          $widget: {},
          settings,
          options,
          onChange(callback) {
            this.change = (value) => {
              settings[property] = value;
              callback(value);
            };
            return this;
          },
          updateDisplay() {},
        };
        widgets[property] = widget;
        return widget;
      },
    };
  };
  await state.scene.addMapSourceControls();
  return { ...state, widgets, folders };
}

for (const { methods, defaultMethod, visible } of [
  { methods: [], defaultMethod: null, visible: false },
  { methods: ["active"], defaultMethod: "active", visible: false },
  { methods: ["one"], defaultMethod: null, visible: true },
  { methods: ["one", "two"], defaultMethod: null, visible: true },
  { methods: ["active", "one"], defaultMethod: "active", visible: true },
]) {
  test(`source controls visibility with ${methods.length} sources and default ${defaultMethod}`, async () => {
    const { scene, widgets, folders, loads } = await sourceControlsHarness(
      methods,
      defaultMethod,
    );
    assert.equal(folders.length, visible ? 1 : 0);
    if (!visible) return;
    const selector = widgets["map source"];
    assert.equal(
      selector.options.length,
      methods.length + (defaultMethod === null ? 1 : 0),
    );
    assert.equal(scene._previewMethod, defaultMethod);
    assert.equal(
      scene._sourceMapLabels[defaultMethod],
      selector.settings["map source"],
    );
    assert.equal(loads.length, 0);
    if (defaultMethod === null)
      assert.equal(selector.settings["map source"], "Current map ✓");
  });
}

for (const methods of [["one"], ["one", "two"]]) {
  test(`returning to an unrecorded current map restores editing with ${methods.length} retained sources`, async () => {
    const state = await sourceControlsHarness(methods, null);
    const selector = state.widgets["map source"];
    const originalDisabled = state.controls.map((control) => control._disabled);
    selector.change(state.scene._sourceMapLabels.one);
    const preview = mesh();
    state.loads[0].success({ scene: preview });
    assert.ok(state.controls.every((control) => control._disabled));
    selector.change(state.scene._sourceMapLabels[null]);
    assert.equal(state.loads.length, 1);
    assert.equal(state.scene._previewMethod, null);
    assert.equal(state.scene._previewMesh, null);
    assert.equal(state.active.visible, true);
    assert.equal(state.camera.projectFrame, true);
    assert.equal(state.projection.visible, true);
    assert.equal(state.scene.transformControl.enabled, true);
    assert.deepEqual(
      state.controls.map((control) => control._disabled),
      originalDisabled,
    );
    assert.equal(preview.geometry.disposed, 1);
    assert.equal(preview.material.map.disposed, 1);
    assert.equal(selector.settings["map source"], "Current map ✓");
    assert.deepEqual(state.writes, []);
    await state.scene.activateSourceMap(null);
    await state.scene.deleteSourceMap(null);
    assert.deepEqual(state.writes, []);
    await state.scene.saveSettings();
    assert.deepEqual(state.writes, ["cameras", "scene"]);
  });
}

test("returning to the unrecorded current map cancels a pending source preview", async () => {
  const state = await sourceControlsHarness(["one"], null);
  const selector = state.widgets["map source"];
  selector.change(state.scene._sourceMapLabels.one);
  selector.change(state.scene._sourceMapLabels[null]);
  const late = mesh();
  state.loads[0].success({ scene: late });
  assert.equal(late.geometry.disposed, 1);
  assert.equal(state.scene._previewMethod, null);
  assert.equal(state.scene._previewLoading, false);
  assert.equal(state.active.visible, true);
  assert.equal(state.progress.style.display, "none");
  assert.equal(selector.settings["map source"], "Current map ✓");
  assert.equal(state.scene.transformControl.enabled, true);
  assert.deepEqual(state.writes, []);
});

test("a failed preview restores the unrecorded current-map selection and controls", async () => {
  const state = await sourceControlsHarness(["one"], null);
  const selector = state.widgets["map source"];
  selector.change(state.scene._sourceMapLabels.one);
  state.loads[0].failure(new Error("download failed"));
  assert.equal(state.scene._previewMethod, null);
  assert.equal(selector.settings["map source"], "Current map ✓");
  assert.equal(state.active.visible, true);
  assert.equal(state.scene.transformControl.enabled, true);
  assert.equal(
    state.controls.find((control) => control.property === "pos X")._disabled,
    false,
  );
});

test("preview is read-only and leaves the active mesh and camera references intact", async () => {
  const state = await harness();
  state.scene.previewSourceMap("one");
  const preview = mesh();
  state.loads[0].success({ scene: preview });
  assert.equal(state.scene.sceneMesh, state.active);
  assert.equal(state.active.visible, false);
  assert.equal(state.camera.mesh, state.projection);
  assert.equal(state.projection.visible, false);
  assert.equal(state.camera.projectFrame, false);
  assert.ok(state.controls.every((control) => control._disabled));
  await state.scene.saveSettings();
  assert.deepEqual(state.writes, []);
});

test("a stale load cannot replace the latest successful selection", async () => {
  const state = await harness();
  state.scene.previewSourceMap("one");
  state.scene.previewSourceMap("two");
  const latest = mesh();
  const stale = mesh();
  state.loads[1].success({ scene: latest });
  state.loads[0].success({ scene: stale });
  assert.equal(state.scene._previewMethod, "two");
  assert.equal(state.scene._previewMesh, latest);
  assert.equal(stale.geometry.disposed, 1);
  assert.equal(stale.material.map.disposed, 1);
});

test("Save is blocked while a preview loads", async () => {
  const state = await harness();
  state.scene.previewSourceMap("one");
  await state.scene.saveSettings();
  assert.deepEqual(state.writes, []);
  assert.equal(state.scene._previewMethod, "active");
});

test("preview applies its complete stored transform without modifying the active map", async () => {
  const state = await harness();
  state.scene.previewSourceMap("one");
  const preview = mesh();
  state.loads[0].success({ scene: preview });
  assert.deepEqual(preview.position.values, [1, 2, 3]);
  assert.deepEqual(preview.rotation.values, [0, Math.PI / 2, 0]);
  assert.deepEqual(preview.scale.values, [2, 3, 4]);
  assert.equal(state.active.position.values, undefined);
  assert.equal(state.scene._mapSourceSettings["map source"], "one");
});

test("a failed load restores editing and the displayed source selection", async () => {
  const state = await harness();
  state.scene._mapSourceSettings["map source"] = "one";
  state.scene.previewSourceMap("one");
  state.loads[0].failure(new Error("download failed"));
  assert.equal(state.scene._previewMethod, "active");
  assert.equal(state.scene._mapSourceSettings["map source"], "active");
  assert.equal(state.active.visible, true);
  assert.equal(state.camera.projectFrame, true);
  assert.equal(state.projection.visible, true);
  assert.equal(state.scene.transformControl.enabled, true);
  assert.equal(
    state.controls.find((control) => control.property === "save")._disabled,
    true,
  );
  assert.equal(
    state.controls.find((control) => control.property === "pos X")._disabled,
    false,
  );
  assert.equal(state.progress.style.display, "none");
});

test("a failed switch keeps the previous preview read-only and selected", async () => {
  const state = await harness();
  state.scene.previewSourceMap("one");
  const preview = mesh();
  state.loads[0].success({ scene: preview });
  state.scene.previewSourceMap("two");
  state.loads[1].failure(new Error("download failed"));
  assert.equal(state.scene._previewMesh, preview);
  assert.equal(state.scene._previewMethod, "one");
  assert.equal(state.scene._mapSourceSettings["map source"], "one");
  await state.scene.saveSettings();
  assert.deepEqual(state.writes, []);
});

test("returning to default restores exact control and projection state without downloading", async () => {
  const state = await harness();
  state.camera.projectFrame = false;
  state.camera.cameraCapture.visible = false;
  state.controls.find((control) => control.property === "save")._disabled =
    false;
  state.scene.previewSourceMap("one");
  const preview = mesh();
  state.loads[0].success({ scene: preview });
  state.scene.previewSourceMap("active");
  assert.equal(state.loads.length, 1);
  assert.equal(state.scene._previewMethod, "active");
  assert.equal(state.scene._previewMesh, null);
  assert.equal(state.active.visible, true);
  assert.equal(state.camera.projectFrame, false);
  assert.equal(state.camera.cameraCapture.visible, false);
  assert.equal(state.projection.visible, true);
  assert.equal(state.scene.transformControl.enabled, true);
  assert.ok(state.controls.every((control) => !control._disabled));
  assert.equal(preview.geometry.disposed, 1);
  assert.equal(preview.material.disposed, 1);
  assert.equal(preview.material.map.disposed, 1);
  assert.equal(state.active.geometry.disposed, 0);
  assert.equal(state.projection.geometry.disposed, 0);
});

test("returning to default cancels a pending preview and disposes its late result", async () => {
  const state = await harness();
  state.scene.previewSourceMap("one");
  state.scene.previewSourceMap("active");
  const stale = mesh();
  state.loads[0].success({ scene: stale });
  assert.equal(state.scene._previewMethod, "active");
  assert.equal(state.active.visible, true);
  assert.equal(stale.geometry.disposed, 1);
});

test("activation requires a successfully displayed preview and cannot run during loading", async () => {
  const state = await harness();
  await state.scene.activateSourceMap("one");
  state.scene.previewSourceMap("one");
  await state.scene.activateSourceMap("one");
  assert.deepEqual(state.writes, []);
  state.loads[0].success({ scene: mesh() });
  await state.scene.activateSourceMap("two");
  assert.deepEqual(state.writes, []);
  await state.scene.activateSourceMap("one");
  assert.deepEqual(state.writes, [["scene", "one"]]);
});

test("switching previews disposes the previous preview but not the active mesh", async () => {
  const state = await harness();
  state.scene.previewSourceMap("one");
  const first = mesh();
  state.loads[0].success({ scene: first });
  state.scene.previewSourceMap("two");
  state.loads[1].success({ scene: mesh() });
  assert.equal(first.geometry.disposed, 1);
  assert.equal(first.material.map.disposed, 1);
  assert.equal(state.active.geometry.disposed, 0);
});

test("shared resources inside a preview are disposed only once", async () => {
  const state = await harness();
  const preview = mesh();
  preview.traverse = (callback) => {
    callback(preview);
    callback(preview);
  };
  state.scene.disposePreviewMesh(preview);
  assert.equal(preview.geometry.disposed, 1);
  assert.equal(preview.material.disposed, 1);
  assert.equal(preview.material.map.disposed, 1);
});

test("normal editing on the active source can still save", async () => {
  const state = await harness();
  await state.scene.saveSettings();
  assert.deepEqual(state.writes, ["cameras", "scene"]);
});

test("an obsolete failure cannot unlock a newer pending preview", async () => {
  const state = await harness();
  state.scene.previewSourceMap("one");
  state.scene.previewSourceMap("two");
  state.loads[0].failure(new Error("obsolete failure"));
  assert.equal(state.scene._previewLoading, true);
  await state.scene.activateSourceMap("one");
  await state.scene.saveSettings();
  assert.deepEqual(state.writes, []);
  state.loads[1].success({ scene: mesh() });
  assert.equal(state.scene._previewMethod, "two");
});

test("unknown sources do not change the preview or load state", async () => {
  const state = await harness();
  state.scene.previewSourceMap("unknown");
  assert.equal(state.loads.length, 0);
  assert.equal(state.scene._previewMethod, "active");
  assert.equal(state.active.visible, true);
});

for (const mapType of ["image", "empty"]) {
  test(`source preview can activate or return to an unrecorded ${mapType} map`, async () => {
    const state = await sourceControlsHarness(["one"], null);
    state.scene.sceneMesh = null;
    state.scene.transformControl = null;
    const floor = mapType === "image" ? mesh() : null;
    state.scene.floorMesh = floor;
    const selector = state.widgets["map source"];
    selector.change(state.scene._sourceMapLabels.one);
    const preview = mesh();
    state.loads[0].success({ scene: preview });
    if (floor) assert.equal(floor.visible, false);
    await state.scene.activateSourceMap("one");
    assert.deepEqual(state.writes, [["scene", "one"]]);
    selector.change(state.scene._sourceMapLabels[null]);
    if (floor) assert.equal(floor.visible, true);
    assert.equal(state.scene._previewMesh, null);
    assert.equal(preview.geometry.disposed, 1);
    assert.equal(state.camera.projectFrame, true);
  });
}

test("editing after returning from preview re-enables the actual Save button", async () => {
  const state = await harness();
  state.scene.previewSourceMap("one");
  state.loads[0].success({ scene: mesh() });
  state.scene.previewSourceMap("active");
  const save = state.controls.find((control) => control.property === "save");
  assert.equal(save.buttonDisabled, true);
  state.scene.updateSaveButton();
  assert.equal(save.buttonDisabled, false);
  state.scene.previewSourceMap("one");
  state.scene.updateSaveButton();
  assert.equal(save.buttonDisabled, true);
  state.scene.previewSourceMap("active");
  state.scene.isStaff = null;
  save.disable();
  state.scene.updateSaveButton();
  assert.equal(save.buttonDisabled, true);
});

test("non-mesh scene settings initialize the retained source selector", async () => {
  const { scene } = await harness();
  let initialized = 0;
  scene.addMapSourceControls = () => {
    initialized++;
  };
  scene.parentFolder = {
    addFolder: () => ({
      add() {
        return {
          onChange() {
            return this;
          },
        };
      },
      close() {},
    }),
  };
  scene.executeOnControl = () => {};
  scene.addControlPanel(false);
  assert.equal(initialized, 1);
});

test("initial Save state, pose edits, and post-save reset stay synchronized", async () => {
  const { scene, controls } = await harness();
  controls.length = 0;
  scene.addMapSourceControls = () => {};
  const folder = {
    add(settings, property) {
      const control = controller(property);
      controls.push(control);
      return control;
    },
    controllersRecursive: () => controls,
    close() {},
  };
  scene.parentFolder = { addFolder: () => folder };
  scene.addControlPanel(false);
  const save = controls.find((control) => control.property === "save");
  assertDisabled(save, true);
  scene.updateSaveButton();
  assertDisabled(save, false);
  await scene.saveSettings();
  assertDisabled(save, true);
  scene.updateSaveButton();
  assertDisabled(save, false);
});

for (const field of ["name", "pixels per meter"]) {
  for (const initiallyDisabled of [false, true]) {
    test(`${field} validation after preview restores Save from disabled=${initiallyDisabled}`, async () => {
      const { scene, controls, loads } = await harness();
      const save = controls.find((control) => control.property === "save");
      save.disable(initiallyDisabled);
      scene.previewSourceMap("one");
      loads[0].success({ scene: mesh() });
      assertDisabled(save, true);
      scene.previewSourceMap("active");
      assertDisabled(save, initiallyDisabled);
      scene.validateField(field, () => false);
      assertDisabled(save, false);
      scene.validateField(field, () => true);
      assertDisabled(save, true);
      scene.validateField(field, () => false);
      assertDisabled(save, false);
      await scene.saveSettings();
      assertDisabled(save, true);
      scene.validateField(field, () => false);
      assertDisabled(save, false);
    });
  }
}

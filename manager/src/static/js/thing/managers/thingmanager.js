// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

import RESTClient from '/static/js/restclient.js';
import SceneCamera from '/static/js/thing/scenecamera.js';
import SceneTripwire from '/static/js/thing/scenetripwire.js';
import SceneRegion from '/static/js/thing/sceneregion.js';
import SceneSensor from '/static/js/thing/scenesensor.js';
import {
  REST_URL,
  SUCCESS
} from '/static/js/constants.js';

let sceneThingObjects = {
  'camera': SceneCamera,
  'tripwire': SceneTripwire,
  'region': SceneRegion,
  'sensor': SceneSensor,
}

let sceneThingAPI = {
  'camera': 'getCameras',
  'tripwire': 'getTripwires',
  'region': 'getRegions',
  'sensor': 'getSensors'
}

export default class ThingManager {
  constructor(sceneID, thingType) {
    this.sceneID = sceneID;
    this.thingType = thingType;
    let authToken = `Token ${document.getElementById("auth-token").value}`;
    this.restclient = new RESTClient(REST_URL, authToken);
    this.sceneThings = {undefined: []}
  }

  async load(params) {
    let apiMethod = sceneThingAPI[this.thingType]
    this.thingsFromDB = await this.restclient[apiMethod]({ scene: this.sceneID });

    if (this.thingsFromDB.statusCode === SUCCESS) {
      for (const thing of this.thingsFromDB.content.results) {
        thing['isStoredInDB'] = true;
        let thingObj = this.add(thing);
        params['currentThings'] = this.sceneThings;
        thingObj.addObject(params);
      }
    }
  }

  setPrivilege(isStaff) {
    this.isStaff = isStaff;
  }

  add(thing) {
    thing['isStaff'] = this.isStaff;
    let thingObj = new sceneThingObjects[this.thingType](thing);
    thingObj.restclient = this.restclient;
    thingObj.sceneID = this.sceneID;
    if (!(thing.uid in this.sceneThings)) {
      this.sceneThings[thing.uid] = thingObj
    }
    else {
      if (thing.uid === undefined) {
        this.sceneThings[thing.uid].push(thingObj)
      }
    }
    return thingObj;
  }

  update(index, params) {
    let thing = this.sceneThings[undefined][index];
    const length = this.sceneThings[undefined].length;
    this.sceneThings[thing.name] = thing;
    this.sceneThings[undefined].splice(index, length);
    this.sceneThings[thing.name].addObject(params);
    return;
  }

  thingObjects() {
    return sceneThingObjects;
  }

  remove() {
    throw new Error("Method needs to be implemented!")
  }

  destroy() {
    throw new Error("Method needs to be implemented!")
  }
}

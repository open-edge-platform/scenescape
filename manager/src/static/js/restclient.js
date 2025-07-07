// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

import * as _ from "/static/assets/axios.min.js";

const _MIN_ERROR_CODE = 400;

export default class RESTClient {
  constructor(url, token, rootcert, timeout = 5000) {
    this.url = url;
    this.rootcert = rootcert;
    this.session = axios.create({ baseURL: this.url, timeout: timeout });
    if (typeof token !== "undefined") {
      this.session.defaults.headers.common["Authorization"] = token;
    }
  }

  async _crud(requestType, endpoint, data, config) {
    try {
      let response = null;
      if (requestType === "GET")
        response = await this.session.get(endpoint, { params: data });
      else if (requestType === "POST")
        response = await this.session.post(endpoint, data);
      else if (requestType === "PUT")
        response = await this.session.put(endpoint, data, config);
      else if (requestType === "DELETE")
        response = await this.session.delete(endpoint);

      return new RESTResult(response);
    } catch (error) {
      if (!("response" in error))
        return new RESTResult({ data: { detail: error.message }, status: 408 });

      return new RESTResult(error.response);
    }
  }

  async authenticate(username, password) {
    let response = await this._crud("POST", "auth", {
      username: username,
      password: password,
    });
    if (response.statusCode == "200") {
      this.session.defaults.headers.common["Authorization"] =
        `Token ${response.content.token}`;
      response.content = { authenticated: true };
    }

    return response;
  }

  async getScenes() {
    return this._crud("GET", "scenes");
  }

  async getScene(uid) {
    return this._crud("GET", `scene/${uid}`);
  }

  async updateScene(uid, data, config) {
    return this._crud("PUT", `scene/${uid}`, data, config);
  }

  async getCameras(data) {
    return this._crud("GET", "cameras", data);
  }

  async createCamera(data) {
    return this._crud("POST", "camera", data);
  }

  async getCamera(uid) {
    return this._crud("GET", `camera/${uid}`);
  }

  async updateCamera(uid, data) {
    return this._crud("PUT", `camera/${uid}`, data);
  }

  async deleteCamera(uid) {
    return this._crud("DELETE", `camera/${uid}`);
  }

  async getTripwires(data) {
    return this._crud("GET", "tripwires", data);
  }

  async createTripwire(data) {
    return this._crud("POST", "tripwire", data);
  }

  async getTripwire(uid) {
    return this._crud("GET", `tripwire/${uid}`);
  }

  async updateTripwire(uid, data) {
    return this._crud("PUT", `tripwire/${uid}`, data);
  }

  async deleteTripwire(uid) {
    return this._crud("DELETE", `tripwire/${uid}`);
  }

  async getRegions(data) {
    return this._crud("GET", "regions", data);
  }

  async createRegion(data) {
    return this._crud("POST", "region", data);
  }

  async getRegion(uid) {
    return this._crud("GET", `region/${uid}`);
  }

  async updateRegion(uid, data) {
    return this._crud("PUT", `region/${uid}`, data);
  }

  async deleteRegion(uid) {
    return this._crud("DELETE", `region/${uid}`);
  }

  async getSensors(data) {
    return this._crud("GET", "sensors", data);
  }

  async createSensor(data) {
    return this._crud("POST", "sensor", data);
  }

  async getSensor(uid) {
    return this._crud("GET", `sensor/${uid}`);
  }

  async updateSensor(uid, data) {
    return this._crud("PUT", `sensor/${uid}`, data);
  }

  async deleteSensor(uid) {
    return this._crud("DELETE", `sensor/${uid}`);
  }

  async getAssets(data) {
    return this._crud("GET", "assets", data);
  }

  async createAsset(data) {
    return this._crud("POST", "asset", data);
  }

  async getAsset(uid) {
    return this._crud("GET", `asset/${uid}`);
  }

  async updateAsset(uid, data) {
    return this._crud("PUT", `asset/${uid}`, data);
  }

  async deleteAsset(uid) {
    return this._crud("DELETE", `sensor/${uid}`);
  }

  async getUsers(data) {
    return this._crud("GET", "users", data);
  }

  async createUser(data) {
    return this._crud("POST", "user", data);
  }

  async getUser(username) {
    return this._crud("GET", `user/${username}`);
  }

  async updateUser(username, data) {
    return this._crud("PUT", `user/${username}`, data);
  }

  async deleteUser(username) {
    return this._crud("DELETE", `user/${username}`);
  }
}

class RESTResult {
  constructor(response) {
    this.content = response.data;
    this.statusCode = response.status;

    if (this.statusCode >= _MIN_ERROR_CODE) {
      this.content = {};
      this.errors = this._parseErrorMessage(response);
    }
  }

  _parseErrorMessage(response) {
    if (response.data.constructor == Object && "detail" in response.data) {
      return response.data.detail;
    }

    if (
      response.data.constructor == Object &&
      "non_field_errors" in response.data
    ) {
      return response.data.non_field_errors.toString();
    }

    return response.statusText;
  }
}

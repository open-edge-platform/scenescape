// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Minimal HTTP proxy for the virtual ONVIF cameras (compose.onvif-cams.yml).
// onvif-server fetches the ONVIF WSDLs and the schemas they import over the
// network at startup. Pointing its http(s)_proxy here serves those files from
// a read-only local cache (see fetch-onvif-schemas.sh) instead, so no internet
// access is needed at runtime. Only GET requests for cached files are
// answered; everything else gets 404 and CONNECT is refused.
//
// Usage: node schema-proxy.js <cache directory> <port>

/* global require, process, URL, console */

"use strict";

const fs = require("fs");
const http = require("http");
const path = require("path");

const cacheDir = path.resolve(process.argv[2] || "/schemas");
const port = Number(process.argv[3] || 18099);

function cachedFile(requestUrl) {
  let parsed;
  try {
    parsed = new URL(requestUrl);
  } catch {
    return null;
  }
  const file = path.resolve(cacheDir, parsed.hostname + parsed.pathname);
  if (!file.startsWith(cacheDir + path.sep)) {
    return null;
  }
  return fs.existsSync(file) && fs.statSync(file).isFile() ? file : null;
}

const server = http.createServer((request, response) => {
  const file = request.method === "GET" ? cachedFile(request.url) : null;
  if (!file) {
    console.warn(
      `schema-proxy: no cached file for ${request.method} ${request.url}`,
    );
    response.writeHead(404, { "Content-Type": "text/plain" });
    response.end("Not cached\n");
    return;
  }
  response.writeHead(200, { "Content-Type": "text/xml; charset=utf-8" });
  fs.createReadStream(file).pipe(response);
});

server.on("connect", (_request, socket) => {
  socket.end("HTTP/1.1 405 Method Not Allowed\r\n\r\n");
});

server.listen(port, "127.0.0.1", () => {
  console.log(`schema-proxy: serving ${cacheDir} on 127.0.0.1:${port}`);
});

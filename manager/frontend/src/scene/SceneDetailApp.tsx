// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { SceneDetailPage } from "./SceneDetailPage";
import type { SceneDetailBootstrap } from "./types";

type Props = {
  bootstrap: SceneDetailBootstrap;
};

export function SceneDetailApp({ bootstrap }: Props) {
  return <SceneDetailPage bootstrap={bootstrap} />;
}

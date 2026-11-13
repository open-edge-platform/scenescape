# observation_conditioning — Surface-Contact Conditioning Algorithm

This algorithm builds on the **frustum_gaussian** library. It describes the next stage of the
pipeline: consuming frustum observations and applying scene-mesh constraints to resolve
object depth.

> **Status:** Working design notes describing the implemented algorithm. Unresolved problems,
> heuristics to revisit, and corner cases are collected in the **Future Work** section at the end.

### Role in the pipeline

`frustum_gaussian` converts each 2D detection into a ray-elongated 3D Gaussian.
This package takes those Gaussians plus a **static scene mesh** and updates per-object
depth (and depth variance) for physical plausibility—surface contact, occlusion, and
walls. The result is still a per-detection measurement for a downstream tracker or
multi-camera fuser; this library does not associate tracks or fuse cameras.

---

## 1. Overview

`observation_conditioning` consumes the outputs of `project_frustum_batch` (after
transform-to-world) and applies scene-specific constraints:

- **Surface-contact conditioning** — For objects in contact with a known surface (floor,
  shelf, ground), the center ray is intersected with the scene mesh (or terrain model) and the
  Gaussian is conditioned on the resulting contact depth along that ray (scalar meters from the
  camera along $\hat{r}$). This is the primary depth-resolution
  mechanism for the majority of tracked objects and is far more powerful than the shape prior
  alone.
- **`FREE_3D` passthrough** — Objects with no assumed surface contact (drones, suspended items,
  objects of unknown posture) are passed through unconditioned. Their depth is resolved by
  multi-camera ray intersection and/or velocity-bounded temporal filtering.
- (Future work) **Upright-axis flag** — A per-class learnable flag indicating whether the object's longest
  dimension is approximately vertical. When validated from sufficient unoccluded observations,
  it tightens $\sigma_z$ conditioning after the surface hit. This is a learned refinement, not
  an a priori assumption — the default is to leave $\sigma_z$ at the prior width.
- (Future work) **Temporal constraints** — Velocity bounds (from world-coordinate displacement across
  frames), size refinement from unoccluded traversals, and maximum observed extent are
  maintained in tracker state and fed back as tightened shape priors on subsequent calls to
  `project_frustum_batch`.

---

## 2. Interface (input from frustum-gaussian)

Fields below are the frustum-gaussian observation contract. After `transform_to_world`,
`mu`, `Sigma`, `ray`, and the depth scalars are expressed in the world frame before this
library consumes them.

### C++

```cpp
struct FrustumObservation {
    float mu[3];        // 3D position mean in camera frame [x, y, z] (m)
    float Sigma[9];     // 3×3 covariance, row-major (m²)
    float ray[3];       // unit center ray [dx, dy, dz] in camera frame
    float depth_est;    // MAP depth estimate along ray (m)
    float depth_sigma;  // 1-σ depth uncertainty (m)
    float depth_lo;     // soft near bound: object is probably beyond this (m)
    float depth_hi;     // soft far bound: object is probably within this (m)
    float score;        // depth constraint quality ∈ [0, 1]
    uint8_t edge_valid; // bit-mask: which bb edges are unclipped
};
```

### Python

```python
"mu":         float32, (N, 3)
"Sigma":      float32, (N, 3, 3)
"ray":        float32, (N, 3)    # batched rays
"depth_est":  float32, (N,)
"depth_sigma": float32, (N,)
"depth_lo":   float32, (N,)
"depth_hi":   float32, (N,)
"score":      float32, (N,)
"edge_valid": uint8,   (N,)
```

### Assumptions

1. The mesh is static.
2. The mesh does not contain the dynamic objects we are tracking / detecting.
3. Scene is continuous.
4. A detection implies visibility: the 2D detector fired because _some_ of the object was seen.
   The centroid and lower probes **may** be occluded — the algorithm classifies _partial_ vs
   _total_ occlusion from the fraction of the object's vertical extent that is blocked (Step 9.5),
   and only a (near-)totally occluded detection is treated as a mis-placed depth prior.
5. Scenes are not facades, but full or partial manifolds (topological).
6. Cameras will be angled downward toward the scene. (Level / upward cameras — see Future Work.)

---

## 3. Algorithm

## Step 0: Depth Map and Normal Map Creation

These depth/normal maps are a camera-view projection of the static scene mesh: hit distance and
surface normal at each pixel.

The depth map is a dense array that maps each pixel in the camera view to a scene hit.
Building it is a one-time "loading" cost up front; afterwards every lookup is $O(1)$.

**Risks.** Memory footprint and dynamic scenes. This method does not work for dynamic scenes,
since a dynamic scene has no fixed scene-map.

Pixel space maps naturally onto a dense matrix, so we index the depth by pixel:

$$
\text{depth}[x][y] = t_{\text{hit}}
$$

($t_{\text{hit}}$ is the nearest mesh-hit distance along that pixel's ray — formally defined in
Step 6 below.)

We also want the surface normal of the triangle each ray intersects. This can be compressed with
**octahedral encoding**, which reduces a surface normal from 3 coordinates to 2, and is stored
the same way:

$$
\text{normal}[x][y] = \hat{n}
$$

($\hat{n}$ is the surface normal of the triangle hit by $t_{\text{hit}}$.)

### 1. Mapping between pixel space and the image plane (Prior Knowledge: Can be skipped)

**Prior information needed.** The camera intrinsics:

$$
K =
\begin{bmatrix}
a & 0 & c_x & 0 \\
0 & b & c_y & 0 \\
0 & 0 & 1 & 0 \\
\end{bmatrix}
$$

### Pixels → rays

To build the depth map we go from pixels to rays.

**1. Build the pixel grid.** Create a dense matrix spanning pixel space (e.g. $1920 \times 1080$):

$$
\begin{bmatrix}
(0,0) & (0,1) & \cdots & (0,1920) \\
(1080, 0) & (1080,1) & \cdots & (1080,1920)
\end{bmatrix}
$$

**2. Back-project each pixel to a camera-frame ray.** A pixel maps to a point on the virtual
image plane at $(x, y, f)$, which — with the camera center as origin — is also the ray direction.

_(Virtual image-plane figure was not vendored into this tree.)_
(Credit: https://visionbook.mit.edu/imaging_geometry.html)

Since we start from pixel indices $(n, m)$, we invert the intrinsics to recover camera
coordinates $(x, y)$:

$$
x = \frac{n - c_x}{a}, \qquad
y = \frac{m - c_y}{b}, \qquad
z = f
$$

In matrix form:

$$
K^{-1}
\begin{bmatrix}
n \\ m \\ 1
\end{bmatrix}
$$

So all we need is $f$ (equivalently $a$).

**3. Convert the ray from camera space to world space.** The camera-extrinsic convention can be
either camera → world or world → camera; either can be normalized to the convention used here.
We use **camera → world**.

Camera → world (rotation $R$, translation $T$, where $T$ is the camera origin in world
coordinates):

$$
p_w = R\,p_c + T
\qquad\Longleftrightarrow\qquad
p_w =
\begin{bmatrix}
R & T \\
0 & 1
\end{bmatrix}
\begin{bmatrix}
p_c \\ 1
\end{bmatrix}
$$

To get a **direction vector** in world coordinates:

1. **Camera origin in world space** is simply $T$.
2. **Transform the image-plane point** $d_c$ to world coordinates:

$$
d_w =
\begin{bmatrix}
R & T \\
0 & 1
\end{bmatrix}
\begin{bmatrix}
d_c \\ 1
\end{bmatrix}
$$

3. **Subtract the origin** to recover the direction:

$$
\vec{d} = d_w - T
$$

We then pair $\vec{d}$ with the world-space camera center $T$ and raytrace into the mesh using
Open3D.

### 2. Querying for a normal/depth (given a point in world-coords.) (Prior Knowledge: Can be skipped)

To do this we must take a point that exists in real-world-coordinates and convert it to a pixel.

**1. Convert the point from World Coordinates to Camera Coordinates**

$$
p_c =
\begin{bmatrix}
R^\top & -R^\top T \\
0^\top & 1
\end{bmatrix}
\begin{bmatrix}
p_w \\ 1
\end{bmatrix}
$$

**2. Convert the camera coordinates to pixel-coordinates**

Decomposed focal terms $M, N, w, q$ — the height in pixels, width in pixels,
width in meters, and height in meters, respectively. $(X, Y, Z)$ below are the components of
the camera-frame point $p_c$ from Step 1 above.

The image-plane location follows from similar triangles:

$$
\frac{x}{f} = \frac{X}{Z}, \qquad \frac{y}{f} = \frac{Y}{Z}
\quad\Longrightarrow\quad
x = f\frac{X}{Z}, \qquad y = f\frac{Y}{Z}
$$

This gives location in meters. To convert to pixels we use the intrinsics, projecting a camera-frame point to pixels:

$$
\begin{bmatrix}
a & 0 & c_x & 0 \\
0 & b & c_y & 0 \\
0 & 0 & 1 & 0 \\
\end{bmatrix}
\begin{bmatrix}
X \\ Y \\ Z \\ 1
\end{bmatrix} =
\begin{pmatrix}
a\frac{X}{Z} + c_x \\
b\frac{Y}{Z} + c_y
\end{pmatrix} =
\begin{pmatrix}
n \\ m
\end{pmatrix}
$$

> The $(n,m)$ resulting from this equation in all likeliness not converge to an integer, and given there are not partial pixels we will need to round up/down to determine an appropiate location to index.

Where:

$$
a = f\frac{N}{w}, \qquad b = f\frac{M}{q}
$$

and note these may be equal (i.e. $\frac{M}{q} = \frac{N}{w}$).

And:

$$
(c_x, c_y) = \text{Camera Center offsets in relative to Pixel-Space origin}
$$

If the camera center lies on the optical axis and the origin is a right-handed Cartesian frame, the offsets are:

$$
(c_x = N/2,\; c_y = M/2)
$$

Practically, $n, m$ are array indices, so the origin sits at the top-left of the frame. This
makes the scale terms $a, b$ negative: in an array the column index grows rightward and the row
index grows downward, whereas in the image plane (right-handed Cartesian, $Z$ forward from the
camera) the $X$-axis points left and the $Y$-axis points up.

## Step 1: Probe rays around an object's gaussian centroid

We need lateral and vertical rays based in world-coordinates to probe the mesh around the centroid. The quantities
involved are:

$$
\begin{aligned}
\mu       &= \text{camera-frame center} \\
r         &= \text{centroid ray (unit vector)} \\
d_{est}   &= \text{estimated centroid depth} \\
\Sigma    &= \text{elongated-ellipsoid Gaussian covariance} \\
p_c       &= \text{centroid point (on the ray, at depth } d_{est}\text{)} \\
\hat{z}_{\text{up}} &= \text{world-up unit vector, points in the direction of gravity} \\
\mathbf{e}_h, \mathbf{e}_v &= \text{lateral and vertical basis vectors orthogonal to } \hat{r} \\
\Phi      &= \text{orthonormal frame } [\hat{r},\, \mathbf{e}_h,\, \mathbf{e}_v] \\
\Lambda   &= \text{diagonal eigenvalue matrix of } \Sigma \text{ in the frame } \Phi \\
\sigma_h, \sigma_v, \sigma_d &= \text{std. deviations (eigenvalues) along } \mathbf{e}_h,\, \mathbf{e}_v,\, \hat{r} \\
\epsilon  &= \text{probe-extension fraction (} 0.1\sigma \text{), nudges a probe beyond the bounding box}
\end{aligned}
$$

Since $d_{est}$ is the mean of our Gaussian along the ray, and $r$ is a unit vector from the
camera frame, the centroid point is:

$$P_c = r\,d_{est} + \mu$$

From here we extract the horizontal and vertical variance from an objects current covariance and standardize it.

>

#### Step 1: Build the orthonormal frame (eigenvectors)

References: [manual eigendecomposition](<https://math.libretexts.org/Bookshelves/Linear_Algebra/A_First_Course_in_Linear_Algebra_(Kuttler)/07%3A_Spectral_Theory/7.01%3A_Eigenvalues_and_Eigenvectors_of_a_Matrix>),
[numpy eigendecomposition](https://numpy.org/doc/2.1/reference/generated/numpy.linalg.eig.html).

Rather than decomposing algorithmically, we can reconstruct the eigenvectors directly. We know
$\hat{r}$ and $\hat{z}_{\text{up}}$ (the vertical direction orthogonal to the ground):

$$
\Phi = \left[\, \hat{r},\quad
  \mathbf{e}_h = \hat{r} \times \frac{\hat{z}_{\text{up}}} {\|\cdot\|},\quad
  \mathbf{e}_v = \hat{r} \times \mathbf{e}_h \,\right]
$$

This mirrors the frustum-gaussian construction. An orthonormal frame is built around the center
ray $\hat{r}$:

$$
\mathbf{e}_h = \hat{r} \times \frac{\hat{z}_{\text{up}}}{\|\cdot\|}, \quad
\mathbf{e}_v = \hat{r} \times \mathbf{e}_h
$$

and the 3×3 covariance is assembled in eigendecomposition form (guaranteed PSD):

$$
\Sigma_{\text{cam}} = \sigma_h^2\,\mathbf{e}_h\mathbf{e}_h^\top
                    + \sigma_v^2\,\mathbf{e}_v\mathbf{e}_v^\top
                    + \sigma_d^2\,\hat{r}\hat{r}^\top
$$

#### Step 2: Obtain eigenvalues

Diagonalize the covariance matrix:

$$\Lambda = \Phi^\top \Sigma\, \Phi$$

$\mathbf{e}_h$ and $\mathbf{e}_v$ give the directions to move in the lateral and vertical
directions.

#### Step 3: Offset the centroid to lateral / vertical points

$$
\begin{aligned}
p_{h_{po}} &= p_c + 2\sigma_h\,\mathbf{e}_h \\
p_{v_{po}} &= p_c + 2\sigma_v\,\mathbf{e}_v \\
p_{h_{no}} &= p_c - 2\sigma_h\,\mathbf{e}_h \\
p_{v_{no}} &= p_c - 2\sigma_v\,\mathbf{e}_v
\end{aligned}
$$

where $\sigma_h$ and $\sigma_v$ come from the diagonal of the eigenvalue matrix $\Lambda$, and:

- `po` = positive offset
- `no` = negative offset
- `pe` = positively extended
- `ne` = negatively extended

#### Step 4: Derive the probe rays

$$
\begin{aligned}
r_{h_{po}} &= \frac{(p_{h_{po}} - \mu)}{\|\cdot\|} \\
r_{v_{po}} &= \frac{(p_{v_{po}} - \mu)}{ \|\cdot\|} \\
r_{h_{no}} &= \frac{(p_{h_{no}} - \mu)}{\|\cdot\|} \\
r_{v_{no}} &= \frac{(p_{v_{no}} - \mu)}{\|\cdot\|}
\end{aligned}
$$

#### Step 5: Probing beyond the bounding box

To detect occlusion or background, we compare what our lateral/vertical rays report against the
mesh. We nudge each horizontal/vertical ray slightly beyond its current position ($\epsilon = .1\sigma $)<sup>&dagger;</sup>
so it acts as a probe.

$$
\begin{aligned}
p_{h_{pe}} &= p_c + (2+ \epsilon)\sigma_h\,\mathbf{e}_h  \\
p_{v_{pe}} &= p_c + (2+ \epsilon)\sigma_v\,\mathbf{e}_v \\
p_{h_{ne}} &= p_c - (2+ \epsilon)\sigma_h\,\mathbf{e}_h \\
p_{v_{ne}} &= p_c - (2+ \epsilon)\sigma_v\,\mathbf{e}_v
\end{aligned}
$$

$$
\begin{aligned}
r_{h_{pe}} &= (p_{h_{pe}} - \mu) / \|\cdot\| \\
r_{v_{pe}} &= (p_{v_{pe}} - \mu) / \|\cdot\| \\
r_{h_{ne}} &= (p_{h_{ne}} - \mu) / \|\cdot\| \\
r_{v_{ne}} &= (p_{v_{ne}} - \mu) / \|\cdot\|
\end{aligned}
$$

#### Step 6: Mesh hits — depth-map lookup vs. direct ray-cast

Two ways to get a mesh hit are used, depending on the cast origin:

- **Probe points from the camera** (the $2\sigma$ / $2.1\sigma$ probes) are **looked up** in the
  prebuilt depth/normal map (Step 0.2, `query`) — $O(1)$, no re-casting.
- **Casts not originating at the camera** (pin-dropping along $-\hat z$, and the forward / backward
  occlusion projections from a probe point along $\pm\hat r$) are cast **directly** into the mesh
  (`cast_np` → Open3D).

Both resolve the same ray-triangle intersection. Call the mesh

$$
\mathcal{M} = \{T_1, T_2, \dots, T_{N_T}\}.
$$

Where $T_j$ is one of the $N_T$ triangles in the mesh ($N_T$ is unrelated to the pixel-width $N$
from Step 0).

We cast the rays $r_{h_\ast}, r_{v_\ast}$ into $\mathcal{M}$, where

$$
\mathbf{r}(t)=\mathbf{o}+t\mathbf{d},\quad t\in [t_{\min },t_{\max }]
$$

Where $\mathbf{o}, \mathbf{d}$ are the ray origin and unit direction.

Using barycentric coordinates and the Moller-Trumbore algorithm we can determine the nearest mesh hit (intersection), given by:

$$
t_{\text{hit}}=\min _{j}\{t_{j}\mid \text{valid}(t_{j},u_{j},v_{j})\}
$$

- $t_j, u_j, v_j$ — the ray parameter and barycentric coordinates of the intersection with
  triangle $T_j$, as solved by Moller–Trumbore.
- $\text{valid}(t_j, u_j, v_j)$ — true only if $t_j \in [t_{\min}, t_{\max}]$ and $(u_j, v_j)$
  lie inside the triangle ($u_j, v_j \ge 0$, $u_j + v_j \le 1$).
- $t_{\text{hit}}$ — the smallest valid $t_j$ over all triangles, i.e. the nearest mesh hit.

_The math here is purposely kept minimal as this is a well known problem already implemented in many libraries (like open3d)_.

#### Step 7: Determining if FREE_3D (Floating)

`FREE_3D` objects skip surface-contact conditioning; depth is left for multi-view / temporal fusion.

To determine if the object we have detected is floating we use the vertical-negative-offset on edge and over edge rays intersections.

For notational simplification, the t_hit for the at-edge vertical ray ($r_{v_{no}}$, the
$2\sigma$ offset probe) will be $h_a$ and the over-edge ray ($r_{v_{ne}}$, the
$(2+\epsilon)\sigma$ extended probe) will be $h_b$; depth_hi (from the `FrustumObservation`
interface) will be $d_h$

$$
f(x) = \begin{cases}
    1 & \text{if } \ h_a > d_h < h_b, \\
    0  & \text{else}
\end{cases}
$$

Where 1 is a boolean indicating **FREE_3D**.

#### Step 8: Determining Occlusion

To determine an occlusion we are using depth discontinuities between $h_a$ and $h_b$. Given that the ground may be slanted and not occluding the expected distance between $h_a$ and $h_b$ will vary. Moreover, in the standard case we can expect that $h_b$ < $h_a$.

Variables:

$$
h_a = \text{depth for at-edge vertical ray (mesh hit of } r_{v_{no}}\text{)} \\
h_b = \text{depth for over-edge vertical ray (mesh hit of } r_{v_{ne}}\text{)} \\
\sigma_r = \sigma_d\text{, the depth-axis std. deviation from Step 1} \\
d_e = d_{est}\text{, the estimated centroid depth from Step 1} \\
$$

##### **Naive Approach (Standalone or pre-filter for Non-Naive)**

The Naive Approach is used either as a standalone occlusion detector OR as a pre-filter that then passes naively identified amodal object to the non-naive detector.

**Check 1: Is at-edge lower probe closer than we expected?**

$$
\begin{aligned}
\epsilon &=.1 \\
\delta_d &= d_e - h_a \\
\text{naive}_a &= \begin{cases}
    1 & \text{if } \delta_d > \epsilon \sigma_r, \\
    0  & \text{if } \delta_d \le \epsilon \sigma_r.
\end{cases}
\end{aligned}
$$

This first check tests if the at-edge vertical probe hits **closer** than the centroid depth
$d_e$ (so $\delta_d = d_e - h_a$ is positive when the probe is closer), using a naive threshold of
$.1\sigma_r$.

**Check 2: Is further hit actually closer?**
Does the at-edge probe hit closer than the over-edge probe (order flip)?
In the standard case $h_b < h_a$, so $h_b - h_a < 0$. The table corner case (at-edge hits the
tabletop, over-edge reaches the ground beneath) flips this to $h_a < h_b$, which is the
occlusion signal.

$$
\begin{aligned}
\delta_e &= h_b - h_a \\
\text{naive}_b &= \begin{cases}
    1 & \text{if } \delta_e > \epsilon \sigma_r, \\
    0  & \text{if } \delta_e \le \epsilon \sigma_r.
\end{cases}
\end{aligned}
$$

**Resolution from Naive Checks**: If either $\text{naive}_a$ or $\text{naive}_b$ fires (given that we are using the naive approach) we determine that there is an occlusion.

**Resolution if we are using the non-naive**: If any point is triggered as occluded from the naive-check, we then pass it forward to be run in the non-naive checks as well.

##### **Non-Naive Approach: Backward Projection** (uses the pin-dropped ground plane below)

Determine the expected intersection point of a ray with the ground. This removes the need for the
heuristic $\epsilon\sigma$: cast from the lower-vertical (over/at) edge point toward and away from
the camera and compare against where the floor is actually expected.

**Pin-dropped averaged ground plane.** Drop $K_p$ pins (not to be confused with the intrinsics
matrix $K$ from Step 0) vertically (along $-\hat{z}$) from points
sampled depthwise along the centroid ray — here over $[\,d_e-\epsilon\sigma_d,\ d_e+\epsilon\sigma_d\,]$
— and intersect each with the mesh for ground hit points $p_{g_k}$ and world-up-oriented normals
$\hat{n}_{g_k}$. Average the hits (missed pins excluded):

$$
\bar{g} = \frac{1}{K_p}\sum_{k} p_{g_k}, \qquad
\bar{n}_g = \frac{\sum_{k}\hat{n}_{g_k}}{\big\lVert \sum_{k}\hat{n}_{g_k} \big\rVert}
$$

This local plane $(\bar g, \bar n_g)$ is what the forward / backward projection below is scored
against.

**Expected floor depth via forward / backward projection.** From the over-premise lower-vertical
probe point $p_o$ (the mesh hit of the over-edge ray $r_{v_{ne}}$, at camera range $h_b$), cast
along the centroid-ray axis both **away from** the camera ($+\hat{r}$,
_forward projection, fpj_) and **toward** it ($-\hat{r}$, _backward projection, bpj_), and take the
mesh hit of each:

$$
t^{\pm} = \text{mesh-hit}(p_o,\; \pm\hat{r},\; \mathcal{M}), \qquad
p^{\pm} = p_o + t^{\pm}(\pm\hat{r}), \qquad
\hat n_{\pm} = \text{hit normal at } p^{\pm}, \qquad
h_{\pm} = p^{\pm}\cdot\hat z
$$

**Trusted projection by cost (not a sign gate).** Rather than a hard above/below-floor sign test,
pick whichever projection better agrees with the pin-dropped averaged ground plane
$(\bar g,\bar n_g)$ above. For each side take its hit-height difference to
the ground height $\bar h_g$ and the angular similarity of its hit normal to $\bar n_g$, normalize
each quantity so the two sides sum to one, and blend with the weight $w =$
`PLANE_DECISION_NML_WEIGHT`:

$$
\text{cost}_{\pm} = w\,\widehat{\text{sim}}_{\pm} + (1-w)\,\widehat{\Delta h}_{\pm}, \qquad
\widehat{\text{sim}}_{\pm} = \frac{\angle(\bar n_g, \hat n_{\pm})}{\angle(\bar n_g,\hat n_{+}) + \angle(\bar n_g,\hat n_{-})}, \quad
\widehat{\Delta h}_{\pm} = \frac{|h_{\pm} - \bar h_g|}{|h_{+}-\bar h_g| + |h_{-}-\bar h_g|}
$$

The lower-cost side is the trusted expected-floor hit $p_{\text{exp}}$. Its distance was measured
along $\pm\hat r$ from $p_o$, while the probe depths are camera ranges, so re-express it as a
camera range:

$$
d_{\text{exp}} = \lVert p_{\text{exp}} - T \rVert
$$

**Occlusion from the expected floor.** Compare the actual camera-cast lower-vertical probe depths
($h_a$ at-edge, $h_b$ over-edge) against the trusted expected-floor range; a side is occluded when
it disagrees by more than $\epsilon$:

$$
\text{occluded}_a = \big| h_a - d_{\text{exp}} \big| > \epsilon, \qquad
\text{occluded}_b = \big| h_b - d_{\text{exp}} \big| > \epsilon
$$

A side's occluder depth is kept when either the non-naive test **or** its naive pre-filter fired,
and the nearer of the two sides is used ($\text{nan} \Rightarrow$ no occlusion):

$$
d_{\text{occ}} = \min\big(\,[\text{occluded}_a \lor \text{naive}_a]\,h_a,\ \ [\text{occluded}_b \lor \text{naive}_b]\,h_b\,\big)
$$

#### Step 9: Determining Wall

Lets get the signed angle between the (potential) wall normal and the world_up angle:

**Reference frame for the signed angle.** The signed angle is measured in the plane whose
normal is $\mathbf{e}_h$. We build a consistent right-handed in-plane basis so the sign is
well-defined. Here $\vec{z} \equiv \hat{z}_{\text{up}}$ (the world-up vector from Step 1) and
$\vec{n}_c$ is the (unnormalized) candidate hit normal from the centroid probe (see $\hat n_c,
d_\text{cand}$ below):

$$
\hat{z} = \frac{\vec{z}}{\lVert \vec{z} \rVert}, \qquad
\hat{n}_c = \frac{\vec{n_c}}{\lVert \vec{n_c} \rVert}, \qquad
\hat{e}_h = \frac{\hat{r} \times \hat{z}}{\lVert \hat{r} \times \hat{z} \rVert}
$$

This matches the $\mathbf{e}_h = \hat r \times \hat z_\text{up}/\|\cdot\|$ construction from Step 1
(same cross-product order, so the sign convention is preserved).

$$
a_s = \text{atan2}\big((\hat{z} \times \hat{n}_c)\cdot \hat{e}_h,\;\; \hat{z}\cdot \hat{n}_c\big)
$$

**Signed vertical/horizontal classification.** Using $a_s$ we can reject surfaces whose slope
runs _with_ the camera ray (downward-away), which should not count as walls. Let $[\,l_v, u_v\,]$
be the vertical band (in degrees, e.g. $l_v = 75^\circ,\ u_v = 115^\circ$; convert $a_s$ from
radians before comparison):

> This is the simplest and best test for a wall.

$$
g(a_s) =
\begin{cases}
1 & \text{if } l_v \le a_s < u_v, \\
0 & \text{otherwise.}
\end{cases}
$$

Here the band $[\,l_v, u_v\,]$ is expressed on the **signed** angle, so surfaces that slope
_away with_ the camera ray fall outside the band and are rejected, while surfaces tilting
_toward_ the ray (a backing) are accepted. A vertical wall (horizontal normal) gives
$\hat{z}\cdot\hat{n}_c \approx 0 \Rightarrow a_s \approx +90^\circ$ under the camera-facing
orientation above, so it lands inside the band. The band $[\,l_v, u_v\,]$ is a heuristic (see
Future Work).

Variables used below:

$$
\begin{aligned}
\hat{n}_c,\, d_{\text{cand}} &= \text{candidate = centroid-probe hit normal and camera depth} \\
p_c,\, p_{top} &= \text{centroid and top probe points (spectrum endpoints)} \\
\hat{z}   &= \text{world-up unit vector}, \qquad \text{height}(p) = p \cdot \hat{z}
\end{aligned}
$$

**Composed wall decision.** The live decision is **angle OR spectrum**, in order:

1. **Angle (primary).** If the candidate (centroid-probe) normal is vertical by the signed test,
   it is a wall at the candidate depth $d_{\text{cand}}$:

$$
g(a_s) = 1 \;\Rightarrow\; \text{wall},\quad d_{\text{wall}} = d_{\text{cand}}
$$

2. **Spectrum (fallback).** Otherwise fall back to the centroid-to-top spectrum below; if it
   fires, the wall depth is the spectrum depth:

$$
\lnot g(a_s) \wedge \text{wall}_{\text{spec}} \Rightarrow \text{wall},\quad d_{\text{wall}} = d_{\text{spec}}
$$

3. **Otherwise** no wall ($d_{\text{wall}} = \text{nan}$). Combined: $\;\text{iswall} = g(a_s)\ \lor\ \text{wall}_{\text{spec}}$.

> An earlier height-based _backing_ path (height checks, a naive single-point plane, and a
> pin-dropped ground classification) is **not** part of the live decision — it produced false
> positives on bumpy floors.

When the candidate normal is **not** vertical (the angle test did not fire), we fall back to a
spectrum of rays to see whether the surface rises as a backing would. This needs no known ground
plane:

> The spectrum is a stand-in until local ground-surface determination is solved robustly (see
> Future Work).
> **Spectrum of rays (centroid to top).** Let $p_c$ be the centroid point and $p_{top}$ the
> Gaussian top point. Sample $M_s$ rays (distinct from the pixel-height $M$ in Step 0) by using
> the target point and casting from $\mu$:

$$
q_i = (1 - t_i)\,p_c + t_i\,p_{top}, \qquad
t_i = \frac{i}{M_s-1}, \quad i = 0,\dots,M_s-1
$$

$$
r_i = \frac{q_i - \mu}{\lVert q_i - \mu \rVert}
$$

Cast each $r_i$ into $\mathcal{M}$ to obtain hit point $p_i$, hit normal $\hat{n}_i$, and hit
distance $t_{hit,i}$. Classify each hit as vertical (wall-like) using the unsigned angle
to $\hat{z}$. Note $a_i = \arccos(\lvert \hat{z}\cdot \hat{n}_i \rvert) \in [0^\circ, 90^\circ]$, so
the test is one-sided (a value above $l_v$ suffices; there is no reachable upper bound here):

$$
a_i = \arccos\!\big(\lvert \hat{z}\cdot \hat{n}_i \rvert\big), \qquad
v_i =
\begin{cases}
1 & \text{if } a_i \ge l_v, \\
0 & \text{otherwise.}
\end{cases}
$$

**Decision from the spectrum (used).** The spectrum fires as a wall if **any** ray strikes a
vertical surface **or** any rising horizontal support exists (defined below):

$$
\text{wall}_{\text{spec}} = \Big(\bigvee_{i} v_i\Big) \ \lor\ \Big(\textstyle\sum_i \text{support}_i > 0\Big)
$$

For horizontal hits, gate on a minimum rise over the previous spectrum point ($\eta = 0.1$,
`height_eps`), with both hits finite:

$$
\text{support}_i =
\begin{cases}
1 & \text{if } v_i = 0 \;\wedge\; i > 0 \;\wedge\; p_{i-1}, p_i \text{ finite} \;\wedge\; \text{height}(p_i) - \text{height}(p_{i-1}) > \eta, \\
0 & \text{otherwise.}
\end{cases}
$$

When there is no vertical hit but supporting higher horizontal hits exist, estimate the wall
distance as the mean hit distance over the monotonically increasing (in height) supporting
rays:

$$
d_{\text{wall}} =
\frac{\displaystyle\sum_{i} \text{support}_i \, t_{\text{hit},i}}
     {\displaystyle\sum_{i} \text{support}_i}
$$

The spectrum wall depth is the nearest vertical hit when one exists, otherwise the supported
$d_{\text{wall}}$ (here $M_s = 8$ rays):

$$
d_{\text{spec}} =
\begin{cases}
\min_i \{\, t_{\text{hit},i} \mid v_i = 1 \,\} & \text{if any } v_i = 1, \\
d_{\text{wall}} & \text{otherwise.}
\end{cases}
$$

#### Step 9.5: Partial vs total occlusion (visibility fraction)

Visibility fraction distinguishes partial occlusion (persist behind occluder) from total silhouette blockage (reinterpret nearer surface as wall).

Occlusion (Step 8) and wall (Step 9) locate the nearest surface along the ray, but not **whether
the object is in front of or behind it**. A nearer surface is ambiguous: it is an **occluder**
(object behind it) only if _part_ of the object is still visible; if the object's **entire**
silhouette is blocked, nothing would be visible and the 2D detector could not have fired — so the
depth prior is wrong and that surface is really a **wall** the object stands in front of.

We disambiguate from how much of the vertical extent is occluded. Fan $M_v$ targets (distinct
from $M_s$ in Step 9 and the pixel-height $M$ in Step 0) from the
lower-vertical probe $p_{v_{no}}$ up to the top probe $p_{v_{po}}$, look each up in the depth map,
and mark it **blocked** when the scene hit is nearer than the target:

$$
q_i = (1-t_i)\,p_{v_{no}} + t_i\,p_{v_{po}}, \quad t_i = \tfrac{i}{M_v-1}, \qquad
\text{blocked}_i = \big[\, t_{\text{hit}}(q_i) < \lVert q_i - T\rVert - \epsilon \,\big]
$$

$$
occ_{frac} = \frac{1}{M_v}\sum_i \text{blocked}_i, \qquad
\text{total} = \big[\, occ_{frac} \ge \tau\,\big]
$$

with $M_v = 9$ rays and threshold $\tau = 0.9$ (`occ_frac`). A graded fraction — rather than an
all-or-nothing lo/centroid/top test — keeps the classification robust to single-probe noise and to
a top that just clears the surface. The threshold is deliberately high: any meaningful visible
fraction means a genuine occluder (keep the object behind it), and only a near-zero visible
fraction flips it.

**Effect on the bounds (fed to Step 10).** For a **total** object we drop the occluder (it is not
behind the surface) and set the wall to the nearest blocking surface, so Step 10 pulls it _in
front_ of that surface:

$$
d_{\text{occ}} \leftarrow \text{nan}, \qquad
d_{\text{wall}} \leftarrow \min_i \big[\text{blocked}_i\big]\, t_{\text{hit}}(q_i) \qquad(\text{total only}).
$$

Partial objects keep the occluder (lower bound) from Step 8 and expand, as before.

#### Step 10: Updating gaussian with new bounds

No need to use Mahalanobis distance since depth is along frame (eigen) vector from covariance matrix - meaning it would simplify to standard z-score calculation even if we used it. Usage of relative values for rays follows from the logic that the less certain we are the less precision we should use.e.  
Recall that we have set $ \epsilon=.1 $ as the point extended beyond ($\pm$) each $2\sigma$ ray.

> **Open question.** It's unresolved whether $p_c$ and $p_{c,\text{no}}$ below should be the raw
> offset points from Step 3 or their mesh-projected hits (i.e. $p_{v_{no}}$ cast onto the mesh) —
> see Future Work. $p_{c,\text{no}}$ is distinct from the $p_{h_{no}}/p_{v_{no}}$ points defined
> in Step 3 and is not otherwise used in the algorithm.

$$
\begin{aligned}
z_e &= \epsilon = .1 \\
z_f &= \frac{|(p_c - p_{c,\text{no}}) \cdot \vec{r}|}{\sigma_d} \\
\delta_z &= |z_e - z_f|
\end{aligned}
$$

This begs the question, do we want a hard cut off like this OR do we want a gradual increase no matter what.

$$
f(x) = \begin{cases}
  0 & \text{if } \delta_z \leq .1, \\
  1 & \text{if } \delta_z > .1
\end{cases}
$$

If it is occluded (1), then we get the error as the difference between the predicted depth and the depth of the occluding object.

$$\delta_d = d_{est} - r_{t_{hit}}$$

where $r_{t_{hit}}$ is the camera-range depth of the occluding surface (i.e. $t_{\text{hit}}$
along the centroid ray $r$, as in Step 6).

The error found here will help us determine how much to expand the variance along the rays axis (depth axis).

In order to prevent unnecessarily inflating the variance, we need to determine how much of this error is already explained by our current variance.

$$Q = \frac{\delta^2_d}{S} = \frac{\delta^2_d}{\sigma_d^2 + R_{occ}} $$

$R_{occ}$ is the measurement-noise variance of the occlusion-surface hit itself (mesh/geometry
noise in $r_{t_{hit}}$) — a tunable/estimated term, analogous to the measurement-noise covariance
$R$ in a Kalman filter, and not derived elsewhere in this document.

Now we won't use the squared normalized inflation directly, however we can use the denominator $S$ as a differencing factor.
Now utilizing ideas from adaptive Kalman filtering, we can directly update our variance using only unaccounted for variance.

$$
\sigma_d^{\prime2} = \sigma_d^{2}  + \frac{1}{k}\max(0, \delta_d^2 - S)
$$

> The $\tfrac{1}{k}$ factor is a tunable damping constant (heuristic), not a derived
> quantity — it controls how aggressively unexplained innovation inflates the depth variance.

Now we bound the (inflated) Gaussian by truncating it to the interval the scene evidence allows.
Both ends may be active: the **occluder** is a near-side lower bound $a = d_{\text{occ}}$ (the
object is at least this far), and the **wall / backing** is a far-side upper bound
$b = d_{\text{wall}}$ (the object is no farther than this) — these $a, b$ are unrelated to the
focal-scale terms $a, b$ from Step 0. Either bound is $\pm\infty$ when that
side did not fire:

$$
a = \begin{cases} d_{\text{occ}} & \text{occluded} \\ -\infty & \text{otherwise} \end{cases}
\qquad
b = \begin{cases} d_{\text{wall}} & \text{walled} \\ +\infty & \text{otherwise} \end{cases}
$$

**Guard — a surface can't be both.** If a detected wall coincides with the occluder
($b \le a + \epsilon$) it is the occluder's own face, not a backing behind the object; the wall is
dropped so the update stays occlusion-only (lower-truncate + inflate → expand) rather than
collapsing onto the single surface.

Here $\bar\mu, \bar\sigma$ are the pre-truncation (post-inflation) depth mean and std., i.e.
$\bar\mu = d_{est}$ and $\bar\sigma = \sqrt{\sigma_d^{\prime 2}}$ from the inflation step above:

$$
\alpha = \frac{a -\bar{\mu}}{\bar{\sigma}}
\text{;} \ \ \ \ \ \
\beta = \frac{b-\bar{\mu}}{\bar{\sigma}}
$$

Using these bounds we can then define the truncated mean as:

$$
\mu_{t} = \bar{\mu} - \bar{\sigma} \cdot \frac{\phi(0,1;\beta) - \phi(0,1;\alpha)}{\Phi(0,1;\beta) - \Phi(0,1;\alpha)}
$$

Furthermore we can define the truncated variance as:

$$
\sigma_{t}^{2} = \bar{\sigma}^2 \cdot (1 - \frac{\beta\phi(0,1;\beta) - \alpha\phi(0,1;\alpha)}{\Phi(0,1;\beta) - \Phi(0,1;\alpha)} - (\frac{\phi(0,1;\beta) - \phi(0,1;\alpha)}{\Phi(0,1;\beta) - \Phi(0,1;\alpha)})^2)
$$

Now, since the actual truncated distribution is unnecessary to propagate through we can just use the calculated mean and variance to moment match them with a normal gaussian.

$$
\mathcal{N}(\mu_t, \sigma_t^2)
$$

**Empty-interval fallback.** When the two bounds cross ($a \ge b$ — the occluder lies _behind_ the
wall, i.e. contradictory evidence) the truncated normal is undefined and the closed-form moments
diverge. In that degenerate case we fall back to the midpoint $\tfrac{1}{2}(a+b)$ with the inflated
prior variance. In practice the moments are evaluated with a numerically stable truncated-normal
routine (`scipy.stats.truncnorm`) rather than the raw $\phi/\Phi$ expressions above.

**No-op cases.** Free-3D objects and objects where neither bound fired pass through unchanged
($\mu' = d_e,\ \sigma'^2 = \sigma_d^2$).

The conditioned Gaussian remains a **per-detection measurement**. Track identity,
multi-camera fusion, and long-term scene state are outside this library.

---

## Future Work

Consolidated open problems, heuristics to revisit, and corner cases (gathered from throughout the
document).

### 1. Best-fit ground plane from pin-dropping (OLS / multi-linear regression)

The local ground plane is currently the **mean** of the pin-hit points with the **normalized mean**
of the pin normals. Replace this with a least-squares / multi-linear-regression best-fit plane over
the pin hits (fit $z = c_0 + c_1 x + c_2 y$, or a total-least-squares plane), which yields a better
normal and offset than averaging. The fit **residual** and the **plane-gradient magnitude** also
become usable signals — e.g. to separate floor noise from a genuine slope/backing, which would
re-enable the disabled wall backing path.

### 2. Outlier rejection in pin-dropping

Pins that land on floor objects, steps, or spurious high points bias the averaged/fitted plane. Add
outlier rejection before averaging/fitting — e.g. a robust fit (RANSAC / Theil–Sen), or dropping
pins whose height or normal deviates beyond ~1$\sigma$ of the set.

### 3. Replace heuristic constants with principled / learned values

Audit every tunable constant in the pipeline and seek a data-driven or geometry-derived replacement
(or at least a documented justification):

| Constant                    | Value                  | Where                                                                  |
| --------------------------- | ---------------------- | ---------------------------------------------------------------------- |
| $\epsilon$                  | 0.1                    | occlusion / same-surface / empty-interval tolerance (Steps 8, 9.5, 10) |
| $l_v,\ u_v$                 | 75°, 115°              | wall vertical-angle band (Step 9 angle test + spectrum)                |
| $\tau$ (`occ_frac`), $M_v$  | 0.9, 9                 | total-occlusion visibility fraction (Step 9.5)                         |
| $k$                         | 2                      | adaptive-inflation damping (Step 10)                                   |
| `PLANE_DECISION_NML_WEIGHT` | 0.7                    | normal-vs-height weight in the fpj/bpj cost (Step 8)                   |
| `height_eps`, $M_s$         | 0.1, 8                 | spectrum rising-support min rise and ray count (Step 9)                |
| probe offset                | $2\sigma$, $2.1\sigma$ | at-/over-premise probes ($\epsilon = 0.1\sigma$ extension, Steps 1/5)  |

### 4. Ground-plane / above-below determination (cross-cutting)

_(from STEP -1)_ Robustly determine the local ground plane/normal and whether a point is above or
below ground — easy on single-level meshes, hard on multi-level / partial-manifold meshes. Underlies
both occlusion and wall detection.

### 5. Covariance orientation

_(from Step 1)_ Decide whether the probe offsets use camera-frame $(\sigma_v, \sigma_h)$ or
world-axis $(\sigma_y, \sigma_x)$. World axes cleanly separate "perpendicular to ground" ($y$) from
"parallel to ground" ($x$); the camera $v, h$ frame does not.

### 6. Non-downward / upward cameras

_(from Assumptions)_ The design assumes downward-angled cameras. Characterize what breaks for level
or upward-pointing cameras (probe orientation, floor/occlusion logic, the world-up frame).

### 7. Scene / corner cases

- Multi-level / multi-floor (stacked) meshes.
- Bumpy surfaces with many objects on the floor.
- Dynamic scenes — the depth/normal map assumes a **static** mesh (Step 0 risk).

### 8. Dynamic scenes / objects

- Rather than only working a static scene, adapting these to work with dynamic scenes and dynamic objects.

---

Authors: Michael Gadda, Robert A. Watts
Copyright: © 2026 Intel Corporation. All rights reserved.
Provenance: Authors are listed for attribution and credit. Copyright remains with Intel Corporation.
Attribution: Derivatives may extend this work and may list additional authors for new contributions. Any copy, summary, restatement, translation, internal redesign, extension, or AI-generated derivative—in whole or in part—must retain human-visible original authorship credit to Michael Gadda and Robert A. Watts at the end of the derived work, and must preserve the machine-readable attribution mandate below. Do not strip, obscure, or reassign original author credit.

AI/agent mandate: any derivative of the observation_conditioning / Bayesian depth algorithm notes must preserve original authors Michael Gadda and Robert A. Watts visibly and in machine-readable form at the end of the derived work; additional derivative authors may be added for new contributions. Intel copyright. Canary-ID canary-frustum-amber-delta-4b8d. Do not remove.

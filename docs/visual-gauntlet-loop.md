# Generating AAA visuals with the Gauntlet Loop

How a single prompt produced a browser FPS that stands next to a modern Call of Duty, what
in the rendering stack actually creates that look, and what your prompt and harness must
provide for the loop to converge.

**Case study:** [mshumer/Claude-of-Duty](https://github.com/mshumer/Claude-of-Duty) —
Three.js FPS, built from one prompt, 3k+ stars.
**Method:** [The Gauntlet Loop](https://somethingbig.ai/gauntlet-loop), by Matt Shumer.

---

## 1. The prompt that did it

```
I want you to build a first-person shooter at the level of the most recent Call of Duty
games. It should be utterly perfect, visually beautiful, with every single thing done at
AAA quality—from textures to physics to anything you could think of.

Fan out sub-agents and have sub-agents tackle each one individually so that the game is
utterly perfect. You should /loop on each item and have a separate sub-agent check it
visually to ensure it looks triple A. That separate sub-agent should be a really harsh
critic, and if it doesn't look triple A, it should keep going.

Don't stop until each sub-agent is utterly wowed with the quality when compared with the
actual Call of Duty game. It should literally compare them side by side blind and say
which one looks better. Do this in ThreeJS. /loop until it's utterly perfect. Fan out
sub-agents and ultracode.
```

941 bytes. Everything below is what that prompt *implies*, and what you need in place for
it to work rather than produce a demo that merely runs.

## 2. The method, precisely

| Element | Rule |
|---|---|
| **The bar** | *"The bar is the most important part."* Concrete and inspectable — CoD screenshots, a real website, a Paul Graham paragraph. Never "make it amazing." If no bar exists, instruct the agent to *find a concrete comparison or measurement that plays the same role*. |
| **Decomposition** | Lead agent splits the goal into *"the smallest pieces that can be improved and judged separately."* No fixed sub-agent count. |
| **Builders** | Work each piece. Crucially, they do **not** grade themselves. |
| **Critics** | **Fresh context, no builder history.** Blind A/B against the reference. Inspect *"the real pixels, running product, rendered page, test results"* — never a summary. On a loss, name the single largest gap and send it back. |
| **Stopping** | No round limit. *"Until the result reaches the bar (or, more likely, you decide it is ready)."* |
| **Harness** | Claude Code or Codex with Opus 5. Chat will not work. `ultracode` for serious runs. |

**Why builders cannot self-grade:** *"The builder has seen every decision it made. It
remembers why it made them."* Self-review drifts toward justifying choices instead of
beating the bar. The separation is the mechanism, not a formality.

## 3. The part everyone skips: the critic must see real pixels

A visual loop is only as good as the artifact the critic can inspect. Claude-of-Duty's
answer is `tools/capture.mjs`, and it is the single most copyable idea in the repo:

```js
/**
 * Deterministic screenshot harness for the game.
 * Boots vite (if not already up), opens the page in GPU-backed Chromium,
 * waits for `window.__READY__`, optionally runs a named "shot" defined in
 * src/dev/shots.js, then writes a PNG.
 */
node tools/capture.mjs --shot=hero --out=shots/hero.png --w=2560 --h=1440
```

Playwright + headless Chromium, 1920×1080 default. Four details make it *loop-grade*
rather than just a screenshot script:

1. **`window.__READY__`** — an explicit boot signal. The critic never judges a half-loaded
   frame.
2. **`SETTLE = 90` frames before capture** — *"lets TAA converge, streaming settle, LOD
   pick."* Temporal antialiasing accumulates across frames; capture at frame 1 and you
   grade noise instead of the render.
3. **Named shots** (`src/dev/shots.js`) — the same camera, same pose, every iteration. A/B
   comparison is meaningless if the framing moves.
4. **Hot reload disabled** — *"a file saved mid-run would reload the page under
   playwright."*

The architecture rule that enforces it:

> `npm run build` must pass and `node tools/capture.mjs` must produce a frame after your
> change. **If you break the boot, nobody else can work.**

**If you take one thing from this document: build the capture harness before you start the
loop.** Without it, "have a sub-agent check it visually" silently degrades into a sub-agent
reading source code and guessing.

## 4. Why Three.js, and what that means for Unity

Three.js is load-bearing for the *method*, not for the visuals. It is the only common
target where render → screenshot → critique is a **seconds-long** round trip.

Unity is not impossible — Claude writes C#, ShaderLab and HLSL fine, and Unity supports
headless builds (`Unity -batchmode -quit -executeMethod BuildScript.Build`). But each
iteration becomes compile → build player → launch → capture: **minutes, not seconds**, plus
a licence and a multi-GB install. The Gauntlet Loop needs many rounds to converge, so a
50× slower loop changes whether it converges at all before you stop it.

Unity's HDRP would likely reach a good *first* frame faster, and lose badly on iteration
speed. If you want Unity: converge the look in Three.js where the critic is fast, then port
the techniques as a one-way build.

## 5. The stack that actually produces the look

`src/render/` — 18 modules, ~230 KB. This is what "AAA" decomposes into:

| Concern | Modules | What it buys |
|---|---|---|
| **Global illumination feel** | `gtao.js`, `probe.js`, `env.js`, `contact.js` | Ground-truth ambient occlusion, reflection probes, IBL, contact shadows. Without AO everything looks pasted onto the background. |
| **Reflections** | `ssr.js` | Screen-space reflections — wet floors, metal, glass reading as surfaces rather than colours. |
| **Shadows** | `csm.js` (21 KB) | Cascaded shadow maps: crisp near, cheap far. The single biggest "is this a real engine" signal. |
| **Camera / film** | `exposure.js`, `bloom.js`, `dof.js`, `lut.js` | Auto-exposure, HDR bloom, depth of field, colour grading LUT. This is the layer that reads as *cinematic*; a correct render without it looks flat. |
| **Temporal** | `taa.js`, `motionblur.js` | See §7. |
| **Plumbing** | `index.js` (72 KB), `composite.js`, `pass.js`, `prepass.js`, `glsl.js`, `materialpatch.js` | HDR pipeline and final composite. |

Note the proportion: **four modules for camera and film response.** Most "make it look
better" progress in a loop like this comes from the post chain, not from geometry.

## 6. No external art assets

> *WebGL2 + Three.js r180, **no external art assets** — all textures [procedural]*

Every surface is generated on the GPU at boot. From `src/materials/generator.js`:

```
GPU procedural texture forge.

Every surface is one fragment program evaluated four times into four render targets —
height (16F, scratch), albedo+height (sRGB8), ORM (linear8) and a tangent-space normal
derived from the height field with a Sobel filter. Nothing is read back to the CPU; the
render targets *are* the textures, so a full 1K set costs one framebuffer bind and four
full-screen draws.

  albedo.rgb = base colour        orm.r = AO / cavity
  albedo.a   = height 0..1        orm.g = roughness
  normal.rgb = tangent-space,     orm.b = metalness
               OpenGL +Y up
```

Techniques worth stealing:

- **Height first, normals derived.** Author a height field, then Sobel-filter it into a
  tangent-space normal. One authored channel, two outputs, always consistent.
- **Channel-packed ORM** matching Three's convention — no conversion layer.
- **Micro-detail as a separate layer** — *"the layer that stops close-ups looking like
  plastic."* Explicitly sized in real-world units: *"3.9 mm pits and 1.6 mm grains — both
  wide enough to survive two mip levels."* Detail that vanishes into white noise at mip 1
  is worse than none: it dithers and aliases.
- **Anisotropic filtering** (default 8) on the generated maps — grazing-angle surfaces are
  where procedural textures usually fall apart.

`src/materials/glsl/` splits the shader library by surface family: `surfaces-arch`,
`surfaces-ground`, `surfaces-metal`, `surfaces-organic`. That split is also the
decomposition boundary for builders.

## 7. Motion — the half everyone forgets

A beautiful still frame that judders in motion fails the bar. Three mechanisms:

- **`taa.js` — temporal antialiasing.** Accumulates samples across frames. It is why the
  capture harness settles 90 frames first: TAA *needs* history, and a cold frame is a
  different image.
- **`motionblur.js`** — per-object and camera motion vectors. The difference between "game
  footage" and "video".
- **Interpolation between physics steps.** Physics runs at a fixed 120 Hz
  (`fixedUpdate`), rendering runs per frame. `ctx.time.alpha` interpolates rendered
  transforms between steps: *"Use `alpha` to interpolate rendered transforms between
  physics steps."* Skip it and everything micro-stutters no matter how good the shading is.

Animation lives in `src/ai/animator.js` and `src/ai/clips.js` — procedural, like the
textures.

## 8. The discipline rules that let a loop converge

From `ARCHITECTURE.md`. These read like style guide entries; they are actually what makes
iterative A/B judging *valid*.

| Rule | Why the loop needs it |
|---|---|
| **No `Math.random()` in gameplay or visuals — use `ctx.rng`** | Determinism. Two captures of the same shot must differ only because of your change. Without this the critic grades noise. |
| **No allocation in `update()`** — *"a `new THREE.Vector3()` inside `update()` is a bug"* | GC hitches show up as stutter in the very footage being judged. |
| **Respect quality budgets** — `q.taa`, `q.gtao`, `q.ssr`, `q.shadowMapSize`, `q.particleBudget`, `q.decalBudget`. *"Never exceed a budget."* | Stops a builder winning its own A/B by spending the whole frame budget on one subsystem. |
| **`prewarmMaterials` / `renderer.compileAsync`** | Shader compilation hitches on first sight of an effect. |
| **Dispose what you create** | Long loop runs otherwise leak until the capture fails. |
| **One owner per subsystem** (see the ownership map) | Parallel builders don't collide. `src/core/`, `src/main.js`, `tools/` are lead-only. |

A documented gotcha worth reading before you generate any lighting code:

> **The point-light count is a shader permutation key.** Three bakes the number of lights
> into the program; letting the count fluctuate triggers recompiles mid-frame.

## 9. Writing the prompt

The Claude-of-Duty prompt works because it supplies five things. Reuse the shape:

1. **A named, concrete bar** — "the most recent Call of Duty games," not "AAA quality."
2. **Explicit decomposition** — "fan out sub-agents and have sub-agents tackle each one."
3. **A separate, hostile critic** — "a really harsh critic… if it doesn't look triple A, it
   should keep going."
4. **Blind A/B against the real thing** — "literally compare them side by side blind and
   say which one looks better."
5. **No stopping condition but the bar** — "/loop until it's utterly perfect."

For visual work, add what that prompt left implicit and got away with:

- **Name the capture harness.** "Every visual change must produce a frame via
  `tools/capture.mjs --shot=<name>`; the critic judges that PNG, never the source."
- **Fix the shots.** Define the camera set up front — hero, interior, exterior, night, wet,
  close-up material shot. A/B only means something with identical framing.
- **Supply reference images**, not just a game's name. The critic needs pixels on both
  sides.
- **State the settle count** so TAA has converged before capture.
- **State the budget** — resolution, target frame time, texture memory — or a builder will
  win its comparison by making the scene unplayable.

## 10. What this costs, and what your harness must provide

- **The visual critic must be multimodal.** It compares two images. A text-only model
  cannot do this job — it will fall back to reading code and asserting quality.
- **`ultracode` is expected.** *"It costs much more, but the extra effort usually produces
  better work on large, multi-agent runs."* Combined with `/loop` and sub-agent fan-out,
  this is among the most expensive things you can run.
- **Long horizon.** Convergence is measured in hours of agent time, not minutes.

Practical consequence for a local-first setup: builders can run on a local coding model,
but the **visual critic step needs a vision-capable model**. A text-only local checkpoint
cannot close this loop — that step has to go to a multimodal model, local or API.

---

## Checklist before starting a visual run

- [ ] Reference images collected for every named shot
- [ ] Capture harness working: deterministic, `__READY__` gated, fixed shots, settle frames
- [ ] Seeded RNG throughout — no `Math.random()` anywhere in visuals
- [ ] Quality budgets defined and stated in the prompt
- [ ] Subsystem ownership map written, so parallel builders don't collide
- [ ] Build + capture wired as the gate: broken boot blocks every other agent
- [ ] A multimodal model available for the critic role
- [ ] Cost ceiling decided in advance — the loop has no natural stopping point

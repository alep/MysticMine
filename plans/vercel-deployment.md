# Plan: Vercel (Static) Deployment

## What we have

`build/web/` is pure static output — HTML, WASM, a tar.gz archive, and two downloaded assets
(BrowserFS + the pygame-ce wheel). Any static host works. The complexity is reproducible CI builds
and the COOP/COEP headers some browsers require for WASM.

---

## Step 1 — Add the patched template to git

`build/` is gitignored, but the patched pygbag template lives there:

```
build/web-cache/27613e24ba16d44f2a5c88150c6d64e5.tmpl
```

Without it, a CI build downloads the stock template from CDN and the five patches
(BrowserFS, DPR override, UME force, `gui_divider`, resolution) are lost.

Add a gitignore exception:

```
# .gitignore — add after the existing "build/" line
!build/web-cache/
```

Then add the file:
```bash
git add build/web-cache/27613e24ba16d44f2a5c88150c6d64e5.tmpl
```

**Caveat:** the template filename is an MD5 of the CDN URL. If pygbag is ever upgraded and the
template URL changes, a new hash is used and the committed file becomes dead weight.
A more robust long-term approach is to move all patches into `build_web.sh` as sed
post-processing on the generated `index.html`, then the template cache is irrelevant.

---

## Step 2 — Update `build_web.sh` for CI (no Poetry)

Vercel's build environment has `pip` but not Poetry. Add a fallback:

```bash
# replace the single "poetry run pygbag ..." line with:
if command -v poetry &>/dev/null; then
    poetry run pygbag --build --disable-sound-format-error "$@" .
else
    pip install pygbag==0.9.3 --quiet
    pygbag --build --disable-sound-format-error "$@" .
fi
```

Pin the version (`==0.9.3`) to avoid breakage when upstream releases a new one.

---

## Step 3 — Create `vercel.json`

```json
{
  "buildCommand": "bash build_web.sh",
  "outputDirectory": "build/web",
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "Cross-Origin-Opener-Policy",   "value": "same-origin" },
        { "key": "Cross-Origin-Embedder-Policy", "value": "require-corp" }
      ]
    }
  ]
}
```

`COOP`/`COEP` headers are required for `SharedArrayBuffer`, which Emscripten WASM uses for
threading. Some browsers silently fail without them.

---

## Quick manual deploy (no CI setup)

If you just want to publish now without configuring auto-deploys:

```bash
bash build_web.sh
cd build/web
vercel --prod          # Vercel CLI deploys the directory as-is
```

This bypasses `vercel.json` entirely — Vercel serves the directory as static files and
you set the COOP/COEP headers once in the Vercel dashboard under Project → Headers.

---

## What to do about `build/web-cache/` long-term

The sed-based approach is cleaner: instead of patching the template file, patch `index.html`
after each build in `build_web.sh`. All five patches can be expressed as sed substitutions,
making the build fully reproducible from scratch with no committed cache files.

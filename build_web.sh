#!/usr/bin/env bash
# Build the pygbag/WASM version of MysticMine.
# monorail/data may be a symlink on disk; os.walk doesn't follow symlinks so
# pygbag won't pack it. We temporarily replace it with a real directory.
set -e
cd "$(dirname "$0")"

LINK=monorail/data
TARGET=data/800x600
RESTORE=0

cleanup() {
    if [ "$RESTORE" = "1" ] && [ ! -L "$LINK" ] && [ -d "$LINK" ]; then
        echo "Restoring $LINK symlink..."
        rm -rf "$LINK"
        ln -s "../$TARGET" "$LINK"
    fi
}
trap cleanup EXIT

if [ -L "$LINK" ]; then
    echo "Replacing symlink $LINK with real directory..."
    rm "$LINK"
    cp -r "$TARGET" "$LINK"
    RESTORE=1
fi

poetry run pygbag --build --disable-sound-format-error "$@" .

# pygbag 0.9.3 references browserfs.min.js at a CDN path that returns 404.
# Serve it locally instead (downloaded from jsDelivr on first build).
BFS=build/web/browserfs.min.js
if [ ! -f "$BFS" ]; then
    echo "Downloading BrowserFS..."
    curl -sL "https://cdn.jsdelivr.net/npm/browserfs@1.4.3/dist/browserfs.min.js" -o "$BFS"
fi

# The pygame-ce WASM wheel is referenced by a relative URL in the package index,
# so it must be served locally alongside the game.
WHEEL_DIR=build/web/cdn/cp312
WHEEL="pygame_ce-2.5.7-cp312-cp312-wasm32_bi_emscripten.whl"
if [ ! -f "$WHEEL_DIR/$WHEEL" ]; then
    echo "Downloading pygame_ce WASM wheel..."
    mkdir -p "$WHEEL_DIR"
    curl -sL "https://pygame-web.github.io/cdn/cp312/$WHEEL" -o "$WHEEL_DIR/$WHEEL"
fi

# Patch generated index.html in case the template cache was cleared.
sed -i '' 's|"https://pygame-web.github.io/cdn/0.9.3//browserfs.min.js"|"browserfs.min.js"|g' \
    build/web/index.html 2>/dev/null || true

echo ""
echo "Build complete. To serve locally:"
echo "  cd build/web && python3 -m http.server 8000"
echo "  then open http://localhost:8000"

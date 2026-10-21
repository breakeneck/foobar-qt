#!/bin/bash
# Build and install FoobarQT.app for macOS.
#
# Python is interpreted, not compiled: "rebuilding" means re-assembling the
# bundle around the repo's venv. After changing code in the repo just run
# ./build_app.sh again and relaunch the app — no reinstall of dependencies
# needed unless requirements.txt changed (then run ./setup.sh first).
#
#   ./build_app.sh            -> builds build/FoobarQT.app and installs to /Applications
#   ./build_app.sh --no-install -> only build, leave in build/
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="$SCRIPT_DIR/venv/bin/python"
APP="build/FoobarQT.app"
INSTALL_DIR="/Applications"

if [ ! -x "$VENV_PY" ]; then
    echo "venv not found. Run ./setup.sh first."
    exit 1
fi

echo "Generating icon..."
rm -rf build/AppIcon.iconset "$APP"
mkdir -p build
"$VENV_PY" "$SCRIPT_DIR/appicon.py" build/icon_512.png
mkdir -p build/AppIcon.iconset
for s in 16 32 64 128 256 512; do
    sips -z $s $s build/icon_512.png --out "build/AppIcon.iconset/icon_${s}x${s}.png" >/dev/null
    d=$((s * 2))
    sips -z $d $d build/icon_512.png --out "build/AppIcon.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns build/AppIcon.iconset -o build/AppIcon.icns

echo "Assembling bundle..."
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp build/AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>FoobarQT</string>
    <key>CFBundleDisplayName</key><string>FoobarQT</string>
    <key>CFBundleIdentifier</key><string>com.breakeneck.foobarqt</string>
    <key>CFBundleExecutable</key><string>FoobarQT</string>
    <key>CFBundleIconFile</key><string>AppIcon</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>1.0</string>
    <key>CFBundleVersion</key><string>1</string>
    <key>LSMinimumSystemVersion</key><string>12.0</string>
    <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

# Mach-O stub launcher: LaunchServices refuses to `open` bundles whose
# CFBundleExecutable is a shell script (error -10669 on recent macOS), so a
# tiny compiled stub execs the real launcher script in Resources.
cat > build/stub.c <<'STUB'
#include <unistd.h>
#include <libgen.h>
#include <stdio.h>
#include <stdint.h>
#include <mach-o/dyld.h>
int main(int argc, char** argv) {
    char exe[4096];
    uint32_t size = sizeof(exe);
    if (_NSGetExecutablePath(exe, &size) != 0) return 1;
    char* dir = dirname(exe);           // .../Contents/MacOS
    char script[4096];
    snprintf(script, sizeof(script), "%s/../Resources/run.sh", dir);
    char* args[3] = { "/bin/bash", script, NULL };  // argv must be NULL-terminated
    execv("/bin/bash", args);
    return 127;
}
STUB
# default SDK (27.0 beta) ships malformed .tbd files with CLT-only installs;
# fall back to the newest usable SDK
SDKS="/Library/Developer/CommandLineTools/SDKs"
clang -o "$APP/Contents/MacOS/FoobarQT" build/stub.c 2>/dev/null \
  || clang -o "$APP/Contents/MacOS/FoobarQT" build/stub.c -isysroot "$SDKS/MacOSX26.5.sdk" 2>/dev/null \
  || clang -o "$APP/Contents/MacOS/FoobarQT" build/stub.c -isysroot "$SDKS/MacOSX.sdk"

# Real launcher lives in Resources: pins app identity, runs from the repo
# dir (config.json/db.sqlite3 are relative paths) and strips
# PYTHONPATH/PYTHONHOME so a foreign environment cannot poison the venv.
cat > "$APP/Contents/Resources/run.sh" <<LAUNCH
#!/bin/bash
REPO_DIR="$SCRIPT_DIR"
cd "\$REPO_DIR"
exec env -u PYTHONPATH -u PYTHONHOME "\$REPO_DIR/venv/bin/python" main.py "\$@"
LAUNCH
chmod +x "$APP/Contents/MacOS/FoobarQT" "$APP/Contents/Resources/run.sh"

# conventional bundle metadata
printf 'APPL????' > "$APP/Contents/PkgInfo"

# ad-hoc signature: without any signature Gatekeeper rejects `open`
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || echo "warning: codesign failed"

if [ "$1" != "--no-install" ]; then
    echo "Installing to $INSTALL_DIR..."
    rm -rf "$INSTALL_DIR/FoobarQT.app"
    cp -R "$APP" "$INSTALL_DIR/"
    # re-register with LaunchServices so icon/pinning metadata refreshes
    /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$INSTALL_DIR/FoobarQT.app"
    echo "Installed: $INSTALL_DIR/FoobarQT.app"
else
    echo "Built: $SCRIPT_DIR/$APP"
fi
#!/bin/bash

rm -f *.deb
sudo rm -rf ./build

# Extract version from DEBIAN/control file
VERSION=$(grep -Po '(?<=^Version: ).*' ./DEBIAN/control)

if [ -z "$VERSION" ]; then
  echo "Error: Version not found in DEBIAN/control file."
  exit 1
fi

# Prepare the build directory
echo "Preparing build directory..."
rsync -av --exclude='.git' --exclude='.gitignore' --exclude='README.md' --exclude='dist' --exclude='build.sh' --exclude='usr/share/' ./ ./build/

# Prepare the changelog
echo "Preparing changelog..."
mkdir -p ./build/usr/share/doc/xpressnet-control
gzip -9 -cn ./usr/share/doc/xpressnet-control/changelog > ./build/usr/share/doc/xpressnet-control/changelog.gz
cp ./usr/share/doc/xpressnet-control/copyright ./build/usr/share/doc/xpressnet-control/copyright

# Prepare the man page
echo "Preparing man page..."
mkdir -p ./build/usr/share/man/man1
gzip -9 -cn ./usr/share/man/man1/xpressnet-control.1 > ./build/usr/share/man/man1/xpressnet-control.1.gz

# Ensure all files are owned by root
echo "Setting ownership to root:root..."
sudo chown -R root:root ./build

# Build the .deb package
PACKAGE_NAME="xpressnet-control-${VERSION}.deb"
rm -f "dist/$PACKAGE_NAME"
echo "Building .deb package: $PACKAGE_NAME"
dpkg-deb --build ./build "dist/$PACKAGE_NAME"

# Clean up the build directory
echo "Cleaning up build directory..."
sudo rm -rf ./build

echo "Build complete: $PACKAGE_NAME"

echo "Lintian checking..."
if lintian "dist/$PACKAGE_NAME"; then
    echo "Lintian check passed: No errors or warnings found. 🎉"
else
    echo "Lintian found issues. Please review the output above. ⚠️"
fi

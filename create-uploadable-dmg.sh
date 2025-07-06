#!/bin/bash

set -e

# Set app and volume details
APP_NAME="K-Configurator"
APP_BUNDLE="${APP_NAME}.app"
DMG_NAME="${APP_NAME}.dmg"
VOLUME_NAME="${APP_NAME}"
STAGING_DIR="./dmg-staging"
APP_SOURCE="${APP_BUNDLE}"
BACKGROUND_IMG="4dmg.png"

# Clean up old files
echo "🧹 Cleaning old files..."
rm -rf "$STAGING_DIR" "$DMG_NAME"

# Create staging directory
echo "📁 Creating staging directory..."
mkdir -p "$STAGING_DIR"

# Copy app into staging dir
echo "📦 Copying app into staging..."
cp -R "$APP_SOURCE" "$STAGING_DIR/"

# Don't manually add Applications symlink – create-dmg will do it!

# Run create-dmg
echo "💿 Creating DMG..."


create-dmg \
  --volname "$VOLUME_NAME" \
  --window-pos 200 120 \
  --window-size 600 350 \
  --icon-size 128 \
  --icon "$APP_BUNDLE" 120 150 \
  --app-drop-link 400 150 \
  --background "$BACKGROUND_IMG" \
  "$DMG_NAME" \
  "$STAGING_DIR"


echo "✅ DMG created: $DMG_NAME"


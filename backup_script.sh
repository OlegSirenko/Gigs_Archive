#!/bin/bash

# Backup script for Gigs Archive project
# Backs up important files like databases, environment files, and JSON configs

# Set backup directory
BACKUP_DIR="../backups_auto"
DATE=$(date +"%Y%m%d_%H%M%S")

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR/$DATE"

echo "Starting backup process..."

# Copy important database files
echo "Backing up database files..."
cp gigs_archive.db "$BACKUP_DIR/$DATE/" 2>/dev/null || echo "Warning: gigs_archive.db not found"
cp posters_web.db "$BACKUP_DIR/$DATE/" 2>/dev/null || echo "Warning: posters_web.db not found"
cp articles.db "$BACKUP_DIR/$DATE/" 2>/dev/null || echo "Warning: articles.db not found"

# Copy environment files
echo "Backing up environment files..."
cp .env "$BACKUP_DIR/$DATE/" 2>/dev/null || echo "Warning: .env not found"
cp .env.example "$BACKUP_DIR/$DATE/" 2>/dev/null || echo "Warning: .env.example not found"

# Copy JSON configuration files (if any)
echo "Backing up JSON configuration files..."
find . -name "*.json" -type f -exec cp {} "$BACKUP_DIR/$DATE/" \; 2>/dev/null

# Copy web admin configuration if it exists
if [ -f "web/admins.json" ]; then
    echo "Backing up web admin configuration..."
    cp web/admins.json "$BACKUP_DIR/$DATE/"
fi

# Copy secret key if it exists
if [ -f ".web/.secret_key" ]; then
    echo "Backing up secret key..."
    cp .web/.secret_key "$BACKUP_DIR/$DATE/"
fi

echo "Backup completed successfully to $BACKUP_DIR/$DATE"
echo "Files backed up:"
ls -la "$BACKUP_DIR/$DATE"
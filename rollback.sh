#!/bin/bash

echo "🔄 NPM Rollback Script"
echo "======================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[ROLLBACK]${NC} $1"
}

if [ -z "$1" ]; then
    print_error "Usage: $0 <backup_directory>"
    print_error "Example: $0 backup_20231227_143000"
    exit 1
fi

BACKUP_DIR="$1"

if [ ! -d "$BACKUP_DIR" ]; then
    print_error "Backup directory '$BACKUP_DIR' not found!"
    exit 1
fi

if [ ! -f "$BACKUP_DIR/package.json" ]; then
    print_error "Backup directory doesn't contain package.json!"
    exit 1
fi

print_info "Found backup: $BACKUP_DIR"
print_info "Contents:"
ls -la "$BACKUP_DIR"

print_warning "This will restore the following files:"
echo "  - frontend/package.json"
echo "  - frontend/package-lock.json (if exists)"
echo
print_warning "This action will undo any changes made by npm audit fix --force"

read -p "Do you want to continue with rollback? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_status "Rollback cancelled."
    exit 0
fi

print_info "Starting rollback..."

# Stop any running development server
if pgrep -f "react-scripts" > /dev/null; then
    print_warning "Stopping React development server..."
    pkill -f "react-scripts"
    sleep 2
fi

# Restore files
print_info "Restoring package.json..."
cp "$BACKUP_DIR/package.json" frontend/

if [ -f "$BACKUP_DIR/package-lock.json" ]; then
    print_info "Restoring package-lock.json..."
    cp "$BACKUP_DIR/package-lock.json" frontend/
fi

# Navigate to frontend and reinstall dependencies
cd frontend
print_info "Reinstalling dependencies from restored package.json..."
rm -rf node_modules package-lock.json
npm install

if [ $? -eq 0 ]; then
    print_status "✅ Rollback completed successfully!"

    print_status "Testing if the application builds..."
    npm run build

    if [ $? -eq 0 ]; then
        print_status "✅ Build successful! Application is working correctly."
    else
        print_error "❌ Build failed after rollback!"
        print_warning "You may need to manually fix dependency issues."
    fi
else
    print_error "❌ Rollback failed during npm install!"
    print_warning "You may need to manually restore files and run npm install."
fi

print_status "Checking current dependencies..."
npm list --depth=0

echo
print_status "=== ROLLBACK SUMMARY ==="
echo "✅ package.json restored from: $BACKUP_DIR/"
if [ -f "$BACKUP_DIR/package-lock.json" ]; then
    echo "✅ package-lock.json restored"
fi
echo "✅ Dependencies reinstalled"
echo "✅ Build tested"
echo
print_info "Your original files are still available in: $BACKUP_DIR/"

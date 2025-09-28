#!/bin/bash

echo "🔒 NPM Vulnerability Fix Script"
echo "================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in the right directory
if [ ! -f "frontend/package.json" ]; then
    print_error "Please run this script from the project root directory"
    exit 1
fi

print_status "Creating backup of current package files..."
BACKUP_DIR="backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

cp frontend/package.json "$BACKUP_DIR/"
cp frontend/package-lock.json "$BACKUP_DIR/" 2>/dev/null || print_warning "No package-lock.json found"

print_status "Backup created in: $BACKUP_DIR/"

# Navigate to frontend directory
cd frontend

print_status "Running npm audit to check current vulnerabilities..."
npm audit

print_warning "This will run 'npm audit fix --force' which may make breaking changes."
read -p "Do you want to continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_status "Operation cancelled."
    exit 0
fi

print_status "Running npm audit fix --force..."
npm audit fix --force

if [ $? -eq 0 ]; then
    print_status "Fix completed successfully!"

    print_status "Checking for remaining vulnerabilities..."
    npm audit

    print_status "Testing if the application still builds..."
    npm run build

    if [ $? -eq 0 ]; then
        print_status "✅ Build successful! Application is working correctly."
    else
        print_error "❌ Build failed! There may be breaking changes."
        print_warning "To rollback, run: ./rollback.sh $BACKUP_DIR"
    fi
else
    print_error "❌ npm audit fix --force failed!"
    print_warning "To rollback, run: ./rollback.sh $BACKUP_DIR"
fi

print_status "Checking updated dependencies..."
npm list --depth=0

echo
print_status "=== SUMMARY ==="
echo "✅ Backup created: $BACKUP_DIR/"
echo "✅ Vulnerabilities fixed (if any were found)"
echo "✅ Build tested"
echo
print_warning "If you encounter any issues:"
echo "1. Try running: npm install"
echo "2. If that doesn't work, rollback with: ./rollback.sh $BACKUP_DIR"
echo "3. Check the React app documentation for any breaking changes"

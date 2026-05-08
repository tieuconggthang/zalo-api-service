#!/bin/bash
# Zalo API Service Test Script

set -e

# Configuration
API_BASE="${API_BASE:-http://localhost:10000}"
API_KEY="${API_KEY:-your-super-secret-api-key-change-this}"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "🚀 Zalo API Service Test Script"
echo "=========================================="
echo "API Base: $API_BASE"
echo ""

# Function to make API calls
call_api() {
    local method=$1
    local endpoint=$2
    local data=$3
    local auth=${4:-true}
    
    local headers="-H 'Content-Type: application/json'"
    if [ "$auth" = true ]; then
        headers="$headers -H 'Authorization: Bearer $API_KEY'"
    fi
    
    if [ -n "$data" ]; then
        curl -s -X $method "$API_BASE$endpoint" $headers -d "$data"
    else
        curl -s -X $method "$API_BASE$endpoint" $headers
    fi
}

# Test 1: Health check
echo "🧪 Test 1: Health Check"
response=$(call_api "GET" "/health" "" false)
if echo "$response" | grep -q "healthy\|not_logged_in"; then
    echo -e "${GREEN}✅ Health check passed${NC}"
    echo "Response: $response"
else
    echo -e "${RED}❌ Health check failed${NC}"
    echo "Response: $response"
fi
echo ""

# Test 2: Root endpoint
echo "🧪 Test 2: Root Endpoint"
response=$(call_api "GET" "/" "" false)
if echo "$response" | grep -q "Zalo API Service"; then
    echo -e "${GREEN}✅ Root endpoint passed${NC}"
else
    echo -e "${RED}❌ Root endpoint failed${NC}"
fi
echo ""

# Test 3: Login status
echo "🧪 Test 3: Login Status"
response=$(call_api "GET" "/login/status" "" false)
if echo "$response" | grep -q "logged_in"; then
    echo -e "${GREEN}✅ Login status endpoint passed${NC}"
    logged_in=$(echo "$response" | grep -o '"logged_in": true' || true)
    if [ -n "$logged_in" ]; then
        echo -e "${GREEN}   🔐 Already logged in${NC}"
    else
        echo -e "${YELLOW}   ⚠️ Not logged in - get QR code to login${NC}"
    fi
else
    echo -e "${RED}❌ Login status failed${NC}"
fi
echo ""

# Test 4: QR Code endpoint
echo "🧪 Test 4: QR Code Endpoint"
echo "Testing /qr-code.png..."
response=$(curl -s -o /dev/null -w "%{http_code}" "$API_BASE/qr-code.png")
if [ "$response" = "200" ]; then
    echo -e "${GREEN}✅ QR code available (HTTP 200)${NC}"
    curl -s "$API_BASE/qr-code.png" -o /tmp/test_qr.png
    echo "   Saved to /tmp/test_qr.png"
elif [ "$response" = "404" ]; then
    echo -e "${YELLOW}⚠️ No QR code (HTTP 404) - Request one at /login/qr${NC}"
else
    echo -e "${YELLOW}⚠️ QR endpoint returned HTTP $response${NC}"
fi
echo ""

# If logged in, test messaging endpoints
logged_in=$(call_api "GET" "/login/status" "" false | grep -o '"logged_in": true' || true)
if [ -n "$logged_in" ]; then
    echo "=========================================="
    echo "🔐 Testing Messaging Endpoints (Logged In)"
    echo "=========================================="
    
    # Test 5: Get friends
    echo "🧪 Test 5: Get Friends"
    response=$(call_api "GET" "/friends")
    if echo "$response" | grep -q '"success": true'; then
        count=$(echo "$response" | grep -o '"count": [0-9]*' | grep -o '[0-9]*')
        echo -e "${GREEN}✅ Got friends list (count: $count)${NC}"
    else
        echo -e "${RED}❌ Failed to get friends${NC}"
        echo "Response: $response"
    fi
    echo ""
    
    # Test 6: Get groups
    echo "🧪 Test 6: Get Groups"
    response=$(call_api "GET" "/groups")
    if echo "$response" | grep -q '"success": true'; then
        count=$(echo "$response" | grep -o '"count": [0-9]*' | grep -o '[0-9]*')
        echo -e "${GREEN}✅ Got groups list (count: $count)${NC}"
    else
        echo -e "${RED}❌ Failed to get groups${NC}"
        echo "Response: $response"
    fi
    echo ""
    
    # Test 7: Get account info
    echo "🧪 Test 7: Get Account Info"
    response=$(call_api "GET" "/account")
    if echo "$response" | grep -q '"success": true'; then
        echo -e "${GREEN}✅ Got account info${NC}"
    else
        echo -e "${RED}❌ Failed to get account info${NC}"
        echo "Response: $response"
    fi
    echo ""
    
    # Note about send tests
    echo -e "${YELLOW}ℹ️  Skipping /send tests - requires valid phone numbers${NC}"
    echo "   To test messaging, run:"
    echo "   curl -X POST $API_BASE/send \\"
    echo "     -H 'Authorization: Bearer $API_KEY' \\"
    echo "     -H 'Content-Type: application/json' \\"
    echo "     -d '{\"phone\": \"0987654321\", \"message\": \"Test\"}'"
    
else
    echo -e "${YELLOW}⚠️ Skipping messaging tests - not logged in${NC}"
    echo "   Run: curl $API_BASE/login/qr --output qr.png"
    echo "   Then scan the QR code with Zalo mobile app"
fi

echo ""
echo "=========================================="
echo "✅ Test Complete"
echo "=========================================="

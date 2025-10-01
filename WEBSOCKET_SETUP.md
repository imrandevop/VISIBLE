# 🔌 WebSocket Configuration Guide

Complete guide for WebSocket setup and usage in the VISIBLE platform.

---

## 📡 **WebSocket Endpoints**

### **Development (Local)**
Use `ws://` protocol for local development:

| Service | Endpoint | Purpose |
|---------|----------|---------|
| **Location Services** | `ws://localhost:8000/ws/location/provider/` | Provider location updates |
| **Location Services** | `ws://localhost:8000/ws/location/seeker/` | Seeker search updates |
| **Work Assignment** | `ws://localhost:8000/ws/work/provider/` | Provider work notifications |
| **Work Assignment** | `ws://localhost:8000/ws/work/seeker/` | Seeker work responses |

### **Production (Secure)**
Use `wss://` protocol for production:

| Service | Endpoint | Purpose |
|---------|----------|---------|
| **Location Services** | `wss://api.visibleapp.in/ws/location/provider/` | Provider location updates |
| **Location Services** | `wss://api.visibleapp.in/ws/location/seeker/` | Seeker search updates |
| **Work Assignment** | `wss://api.visibleapp.in/ws/work/provider/` | Provider work notifications |
| **Work Assignment** | `wss://api.visibleapp.in/ws/work/seeker/` | Seeker work responses |

---

## 🔑 **Authentication**

All WebSocket connections require JWT authentication:

```javascript
// Include JWT token in WebSocket headers
const websocket = new WebSocket('wss://api.visibleapp.in/ws/work/provider/', [], {
    headers: {
        'Authorization': `Bearer ${your_jwt_token}`
    }
});
```

---

## 💻 **Frontend Integration**

### **Environment-Based URL Selection**

```javascript
// JavaScript/React Example
function getWebSocketUrl(endpoint) {
    const isDevelopment = process.env.NODE_ENV === 'development';
    const baseUrl = isDevelopment
        ? 'ws://localhost:8000'
        : 'wss://api.visibleapp.in';
    return `${baseUrl}/ws/${endpoint}`;
}

// Usage
const providerSocket = new WebSocket(getWebSocketUrl('work/provider/'));
const seekerSocket = new WebSocket(getWebSocketUrl('work/seeker/'));
```

### **Flutter/Dart Example**

```dart
String getWebSocketUrl(String endpoint) {
  if (kDebugMode) {
    return 'ws://localhost:8000/ws/$endpoint';
  } else {
    return 'wss://api.visibleapp.in/ws/$endpoint';
  }
}

// Usage
final channel = WebSocketChannel.connect(
  Uri.parse(getWebSocketUrl('work/provider/'))
);
```

---

## 📨 **Message Types**

### **Location Services Messages**

#### **Provider Status Update**
```json
{
    "type": "provider_status_update",
    "active": true,
    "category_code": "MS0001",
    "subcategory_code": "SS0001"
}
```

#### **Seeker Search Update**
```json
{
    "type": "seeker_search_update",
    "searching": true,
    "latitude": 11.2588,
    "longitude": 75.8577,
    "category_code": "MS0001",
    "subcategory_code": "SS0001",
    "distance_radius": 5
}
```

### **Work Assignment Messages**

#### **Work Assignment Notification**
```json
{
    "type": "work_assignment",
    "work_id": 123,
    "service_type": "worker",
    "distance": "2.5km",
    "message": "Need help with painting",
    "seeker_latitude": 11.2588,
    "seeker_longitude": 75.8577,
    "created_at": "2025-01-01T10:30:00Z",
    "seeker": {
        "user_id": 456,
        "name": "John Doe",
        "mobile_number": "9876543210",
        "profile_photo": "https://api.visibleapp.in/media/profiles/456/photo.jpg"
    }
}
```

#### **Work Response**
```json
{
    "type": "work_response",
    "work_id": 123,
    "response": "accepted",
    "message": "I'll be there in 30 minutes"
}
```

---

## �� **Connection Handling**

### **Connection with Error Handling**

```javascript
class WebSocketManager {
    constructor(endpoint, token) {
        this.endpoint = endpoint;
        this.token = token;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.connect();
    }

    connect() {
        try {
            const url = this.getWebSocketUrl(this.endpoint);
            this.ws = new WebSocket(url);

            this.ws.onopen = (event) => {
                console.log('✅ WebSocket connected:', this.endpoint);
                this.reconnectAttempts = 0;

                // Send authentication if needed
                this.authenticate();
            };

            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            };

            this.ws.onclose = (event) => {
                console.log('❌ WebSocket disconnected:', event.code);
                this.handleReconnect();
            };

            this.ws.onerror = (error) => {
                console.error('🚨 WebSocket error:', error);
            };

        } catch (error) {
            console.error('Failed to create WebSocket:', error);
        }
    }

    getWebSocketUrl(endpoint) {
        const isDevelopment = process.env.NODE_ENV === 'development';
        const baseUrl = isDevelopment
            ? 'ws://localhost:8000'
            : 'wss://api.visibleapp.in';
        return `${baseUrl}/ws/${endpoint}`;
    }

    authenticate() {
        // Send authentication message if required
        this.send({
            type: 'authenticate',
            token: this.token
        });
    }

    handleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.pow(2, this.reconnectAttempts) * 1000; // Exponential backoff

            console.log(`🔄 Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

            setTimeout(() => {
                this.connect();
            }, delay);
        } else {
            console.error('❌ Max reconnection attempts reached');
        }
    }

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        } else {
            console.warn('⚠️ WebSocket not connected, queuing message');
            // Could implement message queuing here
        }
    }

    handleMessage(data) {
        switch (data.type) {
            case 'work_assignment':
                this.onWorkAssignment(data);
                break;
            case 'work_response':
                this.onWorkResponse(data);
                break;
            case 'new_provider_available':
                this.onNewProvider(data);
                break;
            case 'provider_went_offline':
                this.onProviderOffline(data);
                break;
            default:
                console.log('Unknown message type:', data.type);
        }
    }

    // Override these methods in your implementation
    onWorkAssignment(data) {}
    onWorkResponse(data) {}
    onNewProvider(data) {}
    onProviderOffline(data) {}
}

// Usage
const providerSocket = new WebSocketManager('work/provider/', userToken);
const seekerSocket = new WebSocketManager('work/seeker/', userToken);
```

---

## 🚀 **Production Deployment**

### **SSL Certificate Requirements**

Your production server must have a valid SSL certificate for WSS to work:

- ✅ **Render.com** - Automatically provides SSL certificates
- ✅ **Heroku** - Automatically provides SSL certificates
- ✅ **AWS/DigitalOcean** - Configure SSL certificates manually

### **Testing Production WebSockets**

Test your production WebSocket endpoints:

```bash
# Test with wscat (install: npm install -g wscat)
wscat -c "wss://api.visibleapp.in/ws/work/provider/" -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### **Debugging WebSocket Issues**

1. **Check browser console** for connection errors
2. **Verify SSL certificate** is valid for your domain
3. **Test authentication** - ensure JWT token is valid
4. **Check server logs** for WebSocket connection attempts
5. **Verify CORS settings** if connecting from different domain

---

## ⚠️ **Common Issues**

### **Mixed Content Error**
- **Problem:** Using `ws://` on HTTPS page
- **Solution:** Always use `wss://` for production

### **Authentication Failed**
- **Problem:** JWT token not sent or invalid
- **Solution:** Include valid JWT token in connection

### **Connection Refused**
- **Problem:** Server not running or wrong URL
- **Solution:** Verify server status and URL

### **Reconnection Loops**
- **Problem:** Client reconnecting too frequently
- **Solution:** Implement exponential backoff

---

## 📊 **Monitoring**

Monitor your WebSocket connections in production:

- **Connection counts** - How many active connections
- **Message throughput** - Messages per second
- **Error rates** - Failed connections/messages
- **Latency** - Connection and message delays

---

**🚀 WebSocket system is ready for production with secure WSS protocol!**

Make sure to:
1. ✅ Use `wss://` for all production connections
2. ✅ Test with real SSL certificates
3. ✅ Implement proper error handling and reconnection
4. ✅ Monitor connection health in production
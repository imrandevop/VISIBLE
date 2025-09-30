# 🔔 Push Notification System Setup Guide

Complete implementation of Firebase push notifications and real-time WebSocket communication for work assignments between Seekers and Providers.

---

## 🎯 **What's Been Implemented**

✅ **Firebase Cloud Messaging (FCM)** - Push notifications to mobile devices
✅ **WebSocket Real-time Communication** - Instant notifications via Django Channels
✅ **Work Assignment System** - Complete order management
✅ **Notification Tracking** - Delivery status monitoring
✅ **API Endpoints** - RESTful APIs for all functionality

---

## 🔥 **Step 1: Complete Firebase Setup**

### 1.1 Create Firebase Project
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Click **"Create a project"**
3. Enter project name: `visible-app`
4. Enable Google Analytics (optional)
5. Click **"Create project"**

### 1.2 Generate Service Account Key
1. In Firebase Console → **Project Settings** → **Service accounts** tab
2. Click **"Generate new private key"**
3. Download the JSON file
4. **Rename to `firebase_credentials.json`**
5. **Place in your Django project root** (same level as `manage.py`)

### 1.3 Security Setup
Add to your `.gitignore`:
```
firebase_credentials.json
```

---

## 📱 **Step 2: Test the Implementation**

### 2.1 Start the Server

```bash
# Install any missing dependencies
pip install -r requirements.txt

# Start Redis (required for WebSocket)
# On Windows with Docker: docker run -d -p 6379:6379 redis:alpine
# Or install Redis directly

# Run Django server
python manage.py runserver

# For production with WebSocket support:
# daphne -b 0.0.0.0 -p 8000 VISIBLE.asgi:application
```

### 2.2 Test FCM Token Registration

**API:** `POST /api/1/profiles/fcm-token/`

```bash
curl -X POST http://localhost:8000/api/1/profiles/fcm-token/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"fcm_token": "your_device_fcm_token_here"}'
```

**Expected Response:**
```json
{
  "status": "success",
  "message": "FCM token updated successfully",
  "data": {
    "user_id": "123",
    "user_type": "provider",
    "fcm_token_set": true
  }
}
```

### 2.3 Test Work Assignment

**API:** `POST /api/1/profiles/assign-work/`

```bash
curl -X POST http://localhost:8000/api/1/profiles/assign-work/ \
  -H "Authorization: Bearer SEEKER_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "provider_id": 2,
    "service_type": "worker",
    "message": "Need help with painting work",
    "distance": "2.5km",
    "latitude": 12.345,
    "longitude": 67.890
  }'
```

**Expected Response:**
```json
{
  "status": "success",
  "message": "Work assigned successfully",
  "data": {
    "work_order_id": 1,
    "provider_name": "John Doe",
    "provider_mobile": "9876543210",
    "service_type": "worker",
    "fcm_sent": true,
    "websocket_sent": true,
    "created_at": "2025-01-30T10:30:00Z"
  }
}
```

### 2.4 Test WebSocket Connection

**Provider WebSocket:** `ws://localhost:8000/ws/work/provider/`
**Seeker WebSocket:** `ws://localhost:8000/ws/work/seeker/`

```javascript
// Example JavaScript WebSocket connection
const websocket = new WebSocket('ws://localhost:8000/ws/work/provider/');

websocket.onopen = function(event) {
    console.log('Connected to WebSocket');
};

websocket.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Received notification:', data);

    if (data.type === 'work_assigned') {
        // Handle work assignment notification
        console.log('New work assignment:', data);

        // Provider can respond
        websocket.send(JSON.stringify({
            type: 'work_response',
            work_id: data.work_id,
            accepted: true
        }));
    }
};
```

---

## 🔧 **Available API Endpoints**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/1/profiles/fcm-token/` | Update FCM token |
| `POST` | `/api/1/profiles/assign-work/` | Assign work to provider |
| `GET` | `/api/1/profiles/work-orders/` | Get work orders |
| `PATCH` | `/api/1/profiles/provider-status/` | Update provider status |
| `GET` | `/api/1/profiles/active-providers/` | Get active providers |

### WebSocket Endpoints
| Endpoint | Purpose |
|----------|---------|
| `ws://localhost:8000/ws/work/provider/` | Provider notifications |
| `ws://localhost:8000/ws/work/seeker/` | Seeker notifications |

---

## 📋 **Database Models Created**

### WorkOrder
- Tracks work assignments between seekers and providers
- Stores service details, location, status, timestamps
- Links to your existing User and UserProfile models

### WorkAssignmentNotification
- Tracks notification delivery status
- Monitors FCM and WebSocket message delivery
- Provides audit trail for troubleshooting

### UserProfile Updates
- Added `fcm_token` field for Firebase messaging
- Added `is_active_for_work` field for provider availability

---

## 🔔 **Notification Flow**

```
1. Seeker assigns work via API
2. System creates WorkOrder record
3. Sends FCM push notification to provider
4. Sends WebSocket message as backup
5. Provider receives notification on mobile/web
6. Provider accepts/rejects via WebSocket
7. Seeker gets notified of response
8. System tracks all delivery statuses
```

---

## 🧪 **Testing Scenarios**

### Scenario 1: Complete Assignment Flow
1. Seeker registers FCM token
2. Provider registers FCM token
3. Provider sets status to active
4. Seeker assigns work to provider
5. Provider receives notifications
6. Provider accepts work
7. Seeker receives acceptance notification

### Scenario 2: WebSocket Fallback
1. Provider has invalid/missing FCM token
2. Seeker assigns work
3. FCM fails, WebSocket succeeds
4. Provider still receives notification

### Scenario 3: Offline Provider
1. Provider is offline/disconnected
2. Seeker assigns work
3. FCM delivers to device
4. Provider reconnects and sees notification

---

## 🐛 **Troubleshooting**

### FCM Not Working
- Check Firebase credentials file exists
- Verify FCM token is valid
- Check device notification permissions
- Look at Django logs for errors

### WebSocket Issues
- Ensure Redis is running
- Check WebSocket URL and authentication
- Verify CORS settings if needed
- Test with browser dev tools

### No Notifications
- Check provider `is_active_for_work` status
- Verify `fcm_token` is saved
- Check work assignment API response
- Review notification logs in database

---

## 🚀 **Production Deployment**

### Environment Variables
```bash
# Firebase
FIREBASE_CREDENTIALS_PATH=/path/to/firebase_credentials.json

# Redis for Channels
REDIS_URL=redis://your-redis-url:6379

# Django
DEBUG=False
SECRET_KEY=your-production-secret-key
```

### ASGI Server
```bash
# Use Daphne for WebSocket support
daphne -b 0.0.0.0 -p 8000 VISIBLE.asgi:application

# Or with Gunicorn + Uvicorn workers
gunicorn VISIBLE.asgi:application -k uvicorn.workers.UvicornWorker
```

---

## 📊 **Monitoring & Analytics**

### Database Queries
```sql
-- Check notification delivery rates
SELECT delivery_status, COUNT(*)
FROM profiles_workassignmentnotification
GROUP BY delivery_status;

-- Recent work orders
SELECT * FROM profiles_workorder
ORDER BY created_at DESC LIMIT 10;

-- Active providers
SELECT * FROM profiles_userprofile
WHERE user_type='provider' AND is_active_for_work=true;
```

### Django Admin
- Register models in admin.py to view in Django admin
- Monitor work orders and notifications
- Debug FCM token issues

---

## 🎯 **Next Steps**

1. **Test with real Firebase project and mobile devices**
2. **Set up monitoring and alerting**
3. **Add notification preferences/settings**
4. **Implement notification history for users**
5. **Add push notification analytics**

---

## 📚 **Integration with Frontend**

Your Flutter app should:
1. Initialize Firebase and get FCM token
2. Send FCM token to backend via `/api/1/profiles/fcm-token/`
3. Connect to WebSocket for real-time updates
4. Handle both FCM and WebSocket notifications
5. Send work responses via WebSocket

---

**🚀 Push notification system is now ready for testing!**

Make sure to:
1. ✅ Complete Firebase setup with credentials file
2. ✅ Test with your Flutter app
3. ✅ Monitor notification delivery
4. ✅ Scale Redis for production use
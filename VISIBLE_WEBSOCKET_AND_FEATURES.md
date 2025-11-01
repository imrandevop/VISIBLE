# VISIBLE - Complete Project Documentation
# Part 3: WebSocket and Advanced Features

**Version:** 1.0
**Last Updated:** October 30, 2025

---

## Table of Contents - Part 3

1. [WebSocket Overview](#websocket-overview)
2. [Location WebSocket](#location-websocket)
3. [Work Assignment WebSocket](#work-assignment-websocket)
4. [Chat System](#chat-system)
5. [Notification System](#notification-system)
6. [Wallet System](#wallet-system)
7. [Rating & Review System](#rating--review-system)
8. [Referral System](#referral-system)
9. [Verification System](#verification-system)
10. [Admin Features](#admin-features)

---

## 1. WebSocket Overview

### ASGI Configuration

**File:** `VISIBLE/asgi.py`

```
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddlewareStack(
        URLRouter(
            location_patterns + work_patterns
        )
    ),
})
```

### Authentication

All WebSocket connections require JWT authentication:

```
Connection URL: ws://api.visibleapp.in/ws/work/provider/
Headers:
  Authorization: Bearer <access_token>
```

**Middleware:** `JWTAuthMiddlewareStack`
**File:** `apps/authentication/middleware.py`

**Process:**
1. Extracts token from Authorization header
2. Validates JWT token
3. Loads user from database
4. Sets `scope['user']` for consumer access
5. Falls back to AnonymousUser if invalid

---

### Available WebSocket Endpoints

| Endpoint | Consumer | Purpose |
|----------|----------|---------|
| `ws/location/provider/` | LocationConsumer | Provider location tracking |
| `ws/location/seeker/` | LocationConsumer | Seeker location tracking |
| `ws/work/provider/` | ProviderWorkConsumer | Provider work assignment & chat |
| `ws/work/seeker/` | SeekerWorkConsumer | Seeker work assignment & chat |

---

### Channel Layers

**Configuration:**
- **Production:** Redis-based channel layer
- **Development:** InMemory channel layer (fallback)

**Purpose:**
- Real-time message broadcasting
- Cross-consumer communication
- Group-based messaging

---

## 2. Location WebSocket

**Endpoint:** `ws/location/{user_type}/`
**Consumer:** `LocationConsumer`
**File:** `apps/location_services/consumers/location_consumer.py`
**Routing:** `apps/location_services/routing.py`

### Connection

**Provider Connection:**
```
ws://api.visibleapp.in/ws/location/provider/
Headers: Authorization: Bearer <token>
```

**Seeker Connection:**
```
ws://api.visibleapp.in/ws/location/seeker/
Headers: Authorization: Bearer <token>
```

---

### Message Types

#### 1. Connection Established

**Direction:** Server → Client
**Trigger:** On successful connection

```json
{
  "type": "connection_established",
  "message": "Location WebSocket connected",
  "user_type": "provider"
}
```

---

#### 2. Location Update (Client → Server)

**Direction:** Client → Server
**Purpose:** Update user's real-time location

```json
{
  "type": "location_update",
  "latitude": 28.7041,
  "longitude": 77.1025,
  "accuracy": 10.5
}
```

**Response:**
```json
{
  "type": "location_updated",
  "message": "Location updated successfully",
  "latitude": 28.7041,
  "longitude": 77.1025,
  "timestamp": "2025-10-23T15:30:00Z"
}
```

**Updates:**
- **Provider:** ProviderActiveStatus (latitude, longitude, last_active_at)
- **Seeker:** SeekerSearchPreference (latitude, longitude, last_search_at)

---

#### 3. Update Distance Radius (Seeker Only)

**Direction:** Seeker → Server
**Purpose:** Update search radius and get refreshed provider list

**Request:**
```json
{
  "type": "update_distance_radius",
  "distance_radius": 10,
  "latitude": 28.7041,
  "longitude": 77.1025,
  "category_code": "MS0001",
  "subcategory_code": "SS0001"
}
```

**Field Requirements:**
- `distance_radius` - Integer (1-50 km) - Required
- `latitude` - Float - Required
- `longitude` - Float - Required
- `category_code` - String - Required
- `subcategory_code` - String - Required

**Success Response:**
```json
{
  "type": "distance_updated",
  "distance_radius": 10,
  "providers": [
    {
      "provider_id": "AB12345678",
      "name": "Jane Smith",
      "mobile_number": "9876543210",
      "age": 35,
      "gender": "female",
      "date_of_birth": "1990-01-15",
      "profile_photo": "https://api.visibleapp.in/media/profiles/123/profile_photo.jpg",
      "languages": ["English", "Hindi", "Tamil"],
      "skills": ["Pipe Fitting", "Leak Repair"],
      "description": "15 years experience in plumbing services",
      "years_experience": 15,
      "user_type": "provider",
      "service_type": "worker",
      "service_coverage_area": 25,
      "rating": 4.88,
      "total_reviews": "472K",
      "rating_distribution": {
        "5_star": "450K",
        "4_star": "10K",
        "3_star": "4K",
        "2_star": "3K",
        "1_star": "5K"
      },
      "reviews": [
        {
          "user": "Amitabh",
          "date": "Sep 27, 2025",
          "rating": 5,
          "review": "Excellent service and very professional"
        }
      ],
      "is_verified": false,
      "images": [
        "https://api.visibleapp.in/media/portfolios/123/work1.jpg"
      ],
      "main_category": {
        "code": "MS0001",
        "name": "Plumber"
      },
      "subcategory": {
        "code": "SS0001",
        "name": "Pipe Fitting"
      },
      "all_subcategories": [
        {
          "code": "SS0001",
          "name": "Pipe Fitting"
        },
        {
          "code": "SS0002",
          "name": "Leak Repair"
        }
      ],
      "service_data": {
        "main_category_id": "MS0001",
        "main_category_name": "Plumber",
        "sub_category_ids": ["SS0001", "SS0002"],
        "sub_category_names": ["Pipe Fitting", "Leak Repair"],
        "years_experience": 15,
        "skills": ["Pipe Fitting", "Leak Repair"],
        "description": "Specialized in all plumbing work"
      },
      "distance_km": 2.5,
      "location": {
        "latitude": 28.7041,
        "longitude": 77.1025
      },
      "profile_complete": true,
      "can_access_app": true,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

**Error Responses:**

Invalid radius:
```json
{
  "type": "error",
  "error": "Distance radius must be between 1 and 50 km"
}
```

Missing fields:
```json
{
  "type": "error",
  "error": "distance_radius, latitude, longitude, category_code, and subcategory_code are required"
}
```

Invalid category:
```json
{
  "type": "error",
  "error": "Category with code 'MS0001' or subcategory with code 'SS0001' not found or inactive"
}
```

Permission denied:
```json
{
  "type": "error",
  "error": "Only seekers can update distance radius"
}
```

**Process:**
1. Validates distance_radius is between 1-50 km
2. Validates all required fields present
3. Validates user is a seeker (not provider)
4. Validates category and subcategory exist and are active
5. Updates SeekerSearchPreference in database
6. Queries active providers within new radius using Haversine formula
7. **Filters providers by BOTH:**
   - Provider is within seeker's distance_radius
   - **AND** Seeker is within provider's service_coverage_area
8. Returns only providers who can actually service the seeker's location
9. Returns sorted provider list by distance (closest first)

**Backend File:** `apps/location_services/consumers/location_consumer.py`

---

#### 4. Ping/Pong (Heartbeat)

**Direction:** Client → Server → Client
**Purpose:** Keep connection alive

**Request:**
```json
{
  "type": "ping"
}
```

**Response:**
```json
{
  "type": "pong",
  "timestamp": "2025-10-23T15:30:00Z"
}
```

---

### Disconnection Flow

**On Disconnect:**
1. WebSocket connection closed
2. User marked as offline (if provider)
3. Cleanup channel group membership
4. Log disconnection

---

## 3. Work Assignment WebSocket

**Endpoints:**
- Provider: `ws/work/provider/`
- Seeker: `ws/work/seeker/`

**Consumers:**
- `ProviderWorkConsumer`
- `SeekerWorkConsumer`

**Files:**
- `apps/profiles/consumers/provider_work_consumer.py` (1,575 lines)
- `apps/profiles/consumers/seeker_work_consumer.py` (1,176 lines)
- `apps/profiles/consumers/consumer_utils.py` (shared utilities)
**Routing:** `apps/profiles/routing.py`

---

### Connection

**Provider Connection:**
```
ws://api.visibleapp.in/ws/work/provider/
Headers: Authorization: Bearer <token>
```

**Seeker Connection:**
```
ws://api.visibleapp.in/ws/work/seeker/
Headers: Authorization: Bearer <token>
```

---

### Connection Established

**Direction:** Server → Client
**Trigger:** On successful connection

**Provider:**
```json
{
  "type": "connection_established",
  "message": "Provider work WebSocket connected",
  "user_id": 123,
  "provider_id": "AB87654321"
}
```

**Seeker:**
```json
{
  "type": "connection_established",
  "message": "Seeker work WebSocket connected",
  "user_id": 124
}
```

**Process:**
1. Validates JWT authentication
2. Joins user-specific channel group
3. Loads chat history if active work session exists
4. Sends connection confirmation

---

### Chat History Loaded

**Direction:** Server → Client
**Trigger:** On connection with active WorkSession

```json
{
  "type": "chat_history_loaded",
  "messages": [
    {
      "id": 567,
      "sender": "provider",
      "sender_name": "Jane Smith",
      "message": "I'm on my way",
      "sent_at": "2025-10-23T14:30:00Z",
      "delivery_status": "read"
    },
    {
      "id": 568,
      "sender": "seeker",
      "sender_name": "John Client",
      "message": "Great, see you soon",
      "sent_at": "2025-10-23T14:32:00Z",
      "delivery_status": "delivered"
    }
  ],
  "total_messages": 2
}
```

**Loads:**
- All messages from active WorkSession
- Ordered by sent_at (oldest first)
- Includes sender info and delivery status

---

### Message Types

#### 1. Work Assignment (Seeker → Provider)

**Direction:** Server → Provider
**Trigger:** Seeker assigns work via app

```json
{
  "type": "work_assigned",
  "work_order_id": 234,
  "seeker": {
    "id": 124,
    "name": "John Client",
    "profile_photo": "https://.../photo.jpg"
  },
  "category": {
    "id": 1,
    "name": "Plumber",
    "code": "MS0001"
  },
  "subcategory": {
    "id": 1,
    "name": "Pipe Fitting",
    "code": "SS0001"
  },
  "description": "Kitchen sink is leaking badly",
  "location": {
    "latitude": 28.7041,
    "longitude": 77.1025,
    "distance": "2.5 km"
  },
  "assigned_at": "2025-10-23T15:00:00Z"
}
```

**Also Sent:**
- FCM push notification to provider
- WorkAssignmentNotification record created

---

#### 2. Work Response (Provider → Server)

**Direction:** Provider → Server
**Purpose:** Accept or reject work assignment

**Accept Request:**
```json
{
  "type": "work_response",
  "work_id": 234,
  "accepted": true
}
```

**Reject Request:**
```json
{
  "type": "work_response",
  "work_id": 234,
  "accepted": false
}
```

**On Accept - Response to Provider:**
```json
{
  "type": "work_accepted",
  "message": "Work accepted successfully",
  "work_order_id": 234,
  "session_id": 456,
  "seeker": {
    "id": 124,
    "name": "John Client"
  }
}
```

**On Accept - Notification to Seeker:**
```json
{
  "type": "work_accepted",
  "work_order_id": 234,
  "provider": {
    "id": 123,
    "name": "Jane Smith",
    "provider_id": "AB87654321",
    "rating": "4.50"
  },
  "accepted_at": "2025-10-23T15:05:00Z"
}
```

**On Reject - Response to Provider:**
```json
{
  "type": "work_rejected",
  "message": "Work rejected successfully",
  "work_order_id": 234
}
```

**On Reject - Notification to Seeker:**
```json
{
  "type": "work_rejected",
  "work_order_id": 234,
  "provider_name": "Jane Smith",
  "rejected_at": "2025-10-23T15:05:00Z"
}
```

**Process (Accept):**
1. Updates WorkOrder status: pending → accepted
2. Creates WorkSession with connection_state: active
3. Sends notifications via WebSocket + FCM
4. Both parties can now chat and share mediums

**Process (Reject):**
1. Updates WorkOrder status: pending → rejected
2. Sends notifications via WebSocket + FCM
3. Seeker can assign to another provider

---

#### 3. Communication Mediums Share (Provider → Seeker)

**Direction:** Provider → Server → Seeker
**Purpose:** Share contact methods with seeker

**Request:**
```json
{
  "type": "medium_share",
  "work_id": 234,
  "mediums": {
    "whatsapp": "9876543210",
    "call": "9876543210",
    "telegram": "@janeprovider",
    "map_location": "https://maps.google.com/?q=28.7041,77.1025",
    "instagram": "https://instagram.com/janeprovider"
  }
}
```

**Valid Medium Types:**
- `telegram` - Telegram username/ID
- `whatsapp` - WhatsApp number
- `call` - Phone number
- `map_location` - Google Maps link
- `website` - Website URL
- `instagram` - Instagram profile
- `facebook` - Facebook profile
- `land_mark` - Address/landmark
- `upi_ID` - UPI payment ID

**Response to Provider:**
```json
{
  "type": "mediums_shared",
  "message": "Mediums shared successfully with seeker"
}
```

**Notification to Seeker:**
```json
{
  "type": "mediums_shared",
  "provider_name": "Jane Smith",
  "mediums": {
    "whatsapp": "9876543210",
    "call": "9876543210",
    "telegram": "@janeprovider"
  },
  "shared_at": "2025-10-23T15:10:00Z"
}
```

**Process:**
1. Validates medium types
2. Updates WorkSession.provider_mediums (JSON field)
3. Notifies seeker via WebSocket
4. Seeker can select preferred mediums

---

#### 4. Seeker Medium Selection (Seeker → Provider)

**Direction:** Seeker → Server → Provider
**Purpose:** Seeker selects which mediums to use

**Request:**
```json
{
  "type": "seeker_medium_selection",
  "work_id": 234,
  "selected_mediums": ["whatsapp", "call"]
}
```

**Notification to Provider:**
```json
{
  "type": "seeker_mediums_selected",
  "seeker_name": "John Client",
  "selected_mediums": ["whatsapp", "call"],
  "selected_at": "2025-10-23T15:12:00Z"
}
```

**Process:**
1. Updates WorkSession.seeker_mediums (JSON field)
2. Notifies provider via WebSocket
3. Both parties aware of communication preferences

---

#### 5. Location Update During Work

**Direction:** Client → Server → Other Party
**Purpose:** Share real-time location during active work

**Request:**
```json
{
  "type": "location_update",
  "work_id": 234,
  "latitude": 28.7041,
  "longitude": 77.1025,
  "accuracy": 10.5
}
```

**Response to Sender:**
```json
{
  "type": "location_updated",
  "message": "Location updated successfully"
}
```

**Notification to Other Party:**
```json
{
  "type": "distance_update",
  "distance": "1.8 km",
  "provider_location": {
    "latitude": 28.7051,
    "longitude": 77.1035
  },
  "seeker_location": {
    "latitude": 28.7041,
    "longitude": 77.1025
  },
  "updated_at": "2025-10-23T15:15:00Z"
}
```

**Process:**
1. Updates location in ProviderActiveStatus or SeekerSearchPreference
2. Calculates distance using Haversine formula
3. Broadcasts distance update to other party
4. Real-time tracking during work

---

#### 6. Start Chat (Provider → Server)

**Direction:** Provider → Server
**Purpose:** Initiate chat session

**Request:**
```json
{
  "type": "start_chat",
  "work_id": 234
}
```

**Response to Both Parties:**
```json
{
  "type": "chat_ready",
  "work_order_id": 234,
  "session_id": 456,
  "message": "Chat session is now active",
  "participants": {
    "provider": {
      "id": 123,
      "name": "Jane Smith"
    },
    "seeker": {
      "id": 124,
      "name": "John Client"
    }
  }
}
```

**Process:**
1. Updates WorkSession.chat_started_at = now()
2. Notifies both parties
3. Chat messages can now be sent

---

#### 7. Chat Message

**Direction:** Client → Server → Other Party
**Purpose:** Send anonymous chat message

**Request:**
```json
{
  "type": "chat_message",
  "work_id": 234,
  "message": "I'm arriving in 5 minutes"
}
```

**Response to Sender:**
```json
{
  "type": "message_sent",
  "message_id": 789,
  "sent_at": "2025-10-23T15:20:00Z"
}
```

**Notification to Recipient:**
```json
{
  "type": "chat_message",
  "message_id": 789,
  "sender": "provider",
  "sender_name": "Jane Smith",
  "message": "I'm arriving in 5 minutes",
  "sent_at": "2025-10-23T15:20:00Z",
  "delivery_status": "sent"
}
```

**Process:**
1. Creates ChatMessage record
2. Sets delivery_status: sent
3. Broadcasts to recipient via WebSocket
4. Message stored for 24 hours after session ends

---

#### 8. Message Delivery Status

**Direction:** Client → Server → Sender
**Purpose:** Confirm message delivery/read status

**Message Delivered:**
```json
{
  "type": "message_delivered",
  "message_id": 789
}
```

**Message Read:**
```json
{
  "type": "message_read",
  "message_id": 789
}
```

**Notification to Sender:**
```json
{
  "type": "message_status_update",
  "message_id": 789,
  "status": "read",
  "updated_at": "2025-10-23T15:21:00Z"
}
```

**Process:**
1. Updates ChatMessage.delivery_status
2. Sets delivered_at or read_at timestamp
3. Notifies sender of status change

---

#### 9. Typing Indicator

**Direction:** Client → Server → Other Party
**Purpose:** Show typing status

**Typing Started:**
```json
{
  "type": "typing_indicator",
  "work_id": 234,
  "is_typing": true
}
```

**Typing Stopped:**
```json
{
  "type": "typing_indicator",
  "work_id": 234,
  "is_typing": false
}
```

**Notification to Other Party:**
```json
{
  "type": "typing_status_event",
  "user": "provider",
  "user_name": "Jane Smith",
  "is_typing": true
}
```

**Note:** Not stored in database, real-time only

---

#### 10. User Presence

**Direction:** Server → Client
**Trigger:** User comes online/offline

**Online:**
```json
{
  "type": "user_presence_event",
  "user": "seeker",
  "user_name": "John Client",
  "status": "online",
  "timestamp": "2025-10-23T15:25:00Z"
}
```

**Offline:**
```json
{
  "type": "user_presence_event",
  "user": "provider",
  "user_name": "Jane Smith",
  "status": "offline",
  "timestamp": "2025-10-23T15:30:00Z"
}
```

---

#### 11. Cancel Connection

**Direction:** Client → Server → Other Party
**Purpose:** Cancel active work session

**Request:**
```json
{
  "type": "cancel_connection",
  "work_id": 234,
  "reason": "Customer request"
}
```

**Response to Initiator:**
```json
{
  "type": "connection_cancelled",
  "message": "Work session cancelled successfully",
  "cancelled_at": "2025-10-23T15:35:00Z"
}
```

**Notification to Other Party:**
```json
{
  "type": "connection_cancelled_event",
  "cancelled_by": "seeker",
  "cancelled_by_name": "John Client",
  "reason": "Customer request",
  "work_order_id": 234,
  "cancelled_at": "2025-10-23T15:35:00Z"
}
```

**Process:**
1. Updates WorkOrder status → cancelled
2. Updates WorkSession state → cancelled
3. Sets WorkSession.cancelled_at and cancelled_by
4. Sets ChatMessage.expires_at = cancelled_at + 24 hours
5. Notifies both parties
6. Both users disconnected from work session

---

#### 12. Finish Service (Provider Only)

**Direction:** Provider → Server → Seeker
**Purpose:** Mark service as completed

**Request:**
```json
{
  "type": "finish_service",
  "work_id": 234
}
```

**Response to Provider:**
```json
{
  "type": "service_finished",
  "message": "Service marked as completed",
  "work_order_id": 234,
  "completed_at": "2025-10-23T16:00:00Z"
}
```

**Notification to Seeker:**
```json
{
  "type": "service_finished_event",
  "work_order_id": 234,
  "provider_name": "Jane Smith",
  "message": "Provider has completed the service. Please rate your experience.",
  "completed_at": "2025-10-23T16:00:00Z"
}
```

**Process:**
1. Updates WorkOrder status → completed
2. Updates WorkSession state → completed
3. Sets WorkSession.completed_at and completed_by
4. Sets ChatMessage.expires_at = completed_at + 24 hours
5. Notifies seeker to rate provider
6. Chat remains accessible for 24 hours

---

#### 13. Request Chat History

**Direction:** Client → Server
**Purpose:** Reload chat messages

**Request:**
```json
{
  "type": "request_chat_history",
  "work_id": 234
}
```

**Response:**
```json
{
  "type": "chat_history_loaded",
  "messages": [
    {
      "id": 567,
      "sender": "provider",
      "message": "I'm on my way",
      "sent_at": "2025-10-23T14:30:00Z",
      "delivery_status": "read"
    }
  ],
  "total_messages": 15
}
```

---

#### 14. Ping/Pong (Heartbeat)

**Request:**
```json
{
  "type": "ping"
}
```

**Response:**
```json
{
  "type": "pong",
  "timestamp": "2025-10-23T16:05:00Z"
}
```

---

### Disconnection Flow

**On Disconnect:**
1. Remove from channel groups
2. Mark user as offline (if provider)
3. Close active WebSocket connection
4. Log disconnection
5. Active work sessions remain (can reconnect)

---

## 4. Chat System

### Overview

**Features:**
- Anonymous chat between seeker and provider
- Real-time messaging via WebSocket
- Message delivery and read receipts
- Typing indicators
- Auto-expiration after 24 hours
- Chat history loading on reconnect

---

### ChatMessage Model

**File:** `apps/profiles/work_assignment_models.py`

| Field | Type | Description |
|-------|------|-------------|
| session | ForeignKey(WorkSession) | Parent session |
| sender | ForeignKey(User) | Message sender |
| message | TextField | Message content |
| sent_at | DateTime | Send timestamp |
| delivery_status | CharField | sent/delivered/read |
| delivered_at | DateTime | Delivery time |
| read_at | DateTime | Read time |
| expires_at | DateTime | Auto-delete time |

---

### Message Lifecycle

```
┌──────────────────────────────────────────┐
│ 1. SEND MESSAGE                          │
│    - Client sends via WebSocket          │
│    - Creates ChatMessage (status: sent)  │
│    - Broadcasts to recipient             │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 2. DELIVERY CONFIRMATION                 │
│    - Recipient receives message          │
│    - Sends message_delivered event       │
│    - Updates status → delivered          │
│    - Sets delivered_at timestamp         │
│    - Notifies sender                     │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 3. READ CONFIRMATION                     │
│    - Recipient reads message             │
│    - Sends message_read event            │
│    - Updates status → read               │
│    - Sets read_at timestamp              │
│    - Notifies sender                     │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 4. AUTO-EXPIRATION (24 hours)            │
│    - Session completed/cancelled         │
│    - expires_at = session_end + 24h      │
│    - Messages auto-deleted after expiry  │
│    - Privacy preserved                   │
└──────────────────────────────────────────┘
```

---

### Message Expiration Logic

**File:** `apps/profiles/work_assignment_models.py`

```python
def save(self, *args, **kwargs):
    """Set expiry time based on session state"""
    if not self.expires_at:
        if self.session.connection_state in ['cancelled', 'completed']:
            expiry_time = self.session.cancelled_at or self.session.completed_at
            if expiry_time:
                self.expires_at = expiry_time + timedelta(hours=24)
    super().save(*args, **kwargs)
```

**Expiration Rules:**
- Trigger: Session state becomes cancelled or completed
- Duration: Exactly 24 hours from session end
- Purpose: Privacy and data cleanup
- Implementation: Database index on expires_at for efficient cleanup queries

---

### Chat Features

**Supported:**
- ✅ Text messages (unlimited length)
- ✅ Real-time delivery
- ✅ Typing indicators
- ✅ Message status (sent/delivered/read)
- ✅ Chat history persistence
- ✅ Auto-expiration

**Not Supported (Future):**
- ❌ Image/file sharing
- ❌ Voice messages
- ❌ Message editing
- ❌ Message deletion
- ❌ Message reactions

---

## 5. Notification System

### Firebase Cloud Messaging (FCM)

**File:** `apps/profiles/notification_services.py`
**Integration:** Firebase Admin SDK

---

### Notification Types

**Model:** `WorkAssignmentNotification`
**File:** `apps/profiles/work_assignment_models.py`

| Type | Trigger | Recipient | Title | Body |
|------|---------|-----------|-------|------|
| work_assigned | Seeker assigns work | Provider | "New Work Assignment" | "You have a new work request from [name]" |
| work_accepted | Provider accepts | Seeker | "Work Accepted" | "[Provider] accepted your work request" |
| work_rejected | Provider rejects | Seeker | "Work Rejected" | "[Provider] declined your work request" |
| work_completed | Provider finishes | Seeker | "Service Completed" | "Please rate your experience with [Provider]" |
| work_cancelled | Either party cancels | Other party | "Work Cancelled" | "Work session has been cancelled" |

---

### Notification Delivery

**Delivery Methods:**
- `fcm` - Firebase Cloud Messaging (push notification)
- `websocket` - Real-time WebSocket message

**Delivery Status:**
- `pending` - Not yet sent
- `sent` - Successfully sent
- `delivered` - Confirmed delivered
- `failed` - Failed to deliver

---

### Send Notification Flow

```
┌──────────────────────────────────────────┐
│ 1. CREATE NOTIFICATION                   │
│    - Event occurs (work assigned, etc.)  │
│    - Creates WorkAssignmentNotification  │
│    - Status: pending                     │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 2. SEND FCM                              │
│    - Retrieves user's fcm_token          │
│    - Validates token                     │
│    - Sends via Firebase Admin SDK        │
│    - Updates status: pending → sent      │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 3. SEND WEBSOCKET                        │
│    - Broadcasts to user's channel group  │
│    - Real-time delivery if connected     │
│    - Fallback if not connected           │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 4. CONFIRMATION                          │
│    - FCM delivery receipt (if available) │
│    - Updates status → delivered          │
│    - Sets delivered_at timestamp         │
└──────────────────────────────────────────┘
```

---

### Key Functions

**send_work_assignment_notification()**
**File:** `apps/profiles/work_assignment_models.py`

**Purpose:** Send FCM when work is assigned to provider

**Parameters:**
- work_order - WorkOrder instance
- provider - UserProfile instance

**Process:**
1. Checks provider.fcm_token exists
2. Creates notification record
3. Sends FCM with work details
4. Updates delivery status

---

**send_work_response_notification()**
**File:** `apps/profiles/work_assignment_models.py`

**Purpose:** Send FCM when provider responds to work

**Parameters:**
- work_order - WorkOrder instance
- accepted - Boolean (true/false)

**Process:**
1. Checks seeker.fcm_token exists
2. Creates notification record
3. Sends FCM with response details
4. Updates delivery status

---

**validate_fcm_token()**
**File:** `apps/profiles/work_assignment_models.py`

**Purpose:** Validate FCM token before sending

**Returns:** True if valid, False if invalid

---

### FCM Token Management

**Update Token:**
```
POST /api/1/profiles/update-fcm-token/
Body: {"fcm_token": "firebase_token_here"}
```

**When to Update:**
- On app launch
- When token refreshes (Firebase auto-refresh)
- On login/logout
- On role switch

---

## 6. Wallet System

### Overview

**Features:**
- Balance tracking (INR)
- Transaction history
- 24-hour online subscription for providers (₹20)
- Referral rewards auto-credit
- Transaction audit trail

---

### Wallet Model

**File:** `apps/profiles/models.py`
**Serializer:** `apps/profiles/serializers/wallet_serializers.py`

| Field | Type | Description |
|-------|------|-------------|
| user | OneToOne(UserProfile) | Owner |
| balance | Decimal(10,2) | Current balance |
| currency | CharField | Default: INR |
| last_online_payment_at | DateTime | Last ₹20 charge |
| online_subscription_expires_at | DateTime | Subscription expiry |
| created_at | DateTime | Wallet creation |
| updated_at | DateTime | Last update |

---

### Online Subscription System

**Cost:** ₹20.00
**Duration:** 24 hours
**Purpose:** Provider appears in search results

---

#### Subscription Flow

```
┌──────────────────────────────────────────┐
│ 1. PROVIDER WANTS TO GO ONLINE           │
│    - Checks wallet balance >= ₹20        │
│    - Checks if subscription active       │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 2. DEDUCT CHARGE                         │
│    - Calls wallet.deduct_online_charge() │
│    - Deducts ₹20 from balance            │
│    - Sets expires_at = now() + 24h       │
│    - Creates WalletTransaction (debit)   │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 3. PROVIDER GOES ONLINE                  │
│    - Updates is_active_for_work = true   │
│    - Visible in seeker searches          │
│    - Can receive work assignments        │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 4. SUBSCRIPTION EXPIRES (24 hours)       │
│    - Automatic expiration check          │
│    - Provider must renew to stay online  │
│    - Another ₹20 charge required         │
└──────────────────────────────────────────┘
```

---

#### Check Subscription Status

**Method:** `is_online_subscription_active()`
**File:** `apps/profiles/models.py:372-377`

```python
def is_online_subscription_active(self):
    """Check if 24-hour subscription is active"""
    if self.online_subscription_expires_at:
        return timezone.now() < self.online_subscription_expires_at
    return False
```

**Returns:** True if current time < expiration time

---

#### Deduct Charge

**Method:** `deduct_online_charge()`
**File:** `apps/profiles/models.py:379-405`

```python
def deduct_online_charge(self):
    """Deduct ₹20 for 24-hour online subscription"""
    ONLINE_CHARGE = Decimal('20.00')

    if self.balance < ONLINE_CHARGE:
        return {
            'success': False,
            'message': 'Insufficient balance'
        }

    self.balance -= ONLINE_CHARGE
    self.last_online_payment_at = timezone.now()
    self.online_subscription_expires_at = timezone.now() + timedelta(hours=24)
    self.save()

    # Create transaction record
    WalletTransaction.objects.create(
        wallet=self,
        transaction_type='debit',
        amount=ONLINE_CHARGE,
        description='24-hour online subscription charge',
        balance_after=self.balance
    )

    return {
        'success': True,
        'message': 'Subscription activated for 24 hours'
    }
```

---

### WalletTransaction Model

**File:** `apps/profiles/models.py`
**Serializer:** `apps/profiles/serializers/wallet_serializers.py`

| Field | Type | Description |
|-------|------|-------------|
| wallet | ForeignKey(Wallet) | Parent wallet |
| transaction_type | CharField | credit/debit |
| amount | Decimal(10,2) | Transaction amount |
| description | TextField | Transaction description |
| balance_after | Decimal(10,2) | Balance after transaction |
| created_at | DateTime | Transaction time |

---

### Transaction Types

**Credit (Money Added):**
- Referral rewards (₹100 for referrer, ₹50 for referee)
- Refunds
- Admin credits
- Payment deposits

**Debit (Money Deducted):**
- 24-hour online subscription (₹20)
- Service fees (future)
- Withdrawals (future)

---

### Transaction Descriptions

| Type | Description |
|------|-------------|
| Referral (Referrer) | "Referral reward for referring provider [name]" |
| Referral (Referee) | "Referral reward for joining with code [code]" |
| Online Subscription | "24-hour online subscription charge" |
| Refund | "Refund for work order #[id]" |
| Admin Credit | "Admin credit - [reason]" |

---

### Wallet API

**Get Wallet:**
```
GET /api/1/profiles/wallet/
Response: Balance, transactions, subscription status
```

**Auto-Creation:**
- Wallet created automatically via Django signal
- Triggered on UserProfile creation
- Initial balance: 0.00 INR

**Signal File:** `apps/profiles/signals.py:9-26`

---

## 7. Rating & Review System

### Overview

**Direction:** Seeker → Provider (only)
**Rating Scale:** 1-5 stars
**Review:** Optional text review
**Aggregation:** Real-time average and distribution

---

### ProviderRating Model

**File:** `apps/profiles/models.py`

| Field | Type | Description |
|-------|------|-------------|
| provider | OneToOne(UserProfile) | Provider being rated |
| average_rating | Decimal(3,2) | Average rating (e.g., 4.50) |
| total_reviews | Integer | Total review count |
| five_star_count | Integer | 5-star reviews |
| four_star_count | Integer | 4-star reviews |
| three_star_count | Integer | 3-star reviews |
| two_star_count | Integer | 2-star reviews |
| one_star_count | Integer | 1-star reviews |
| updated_at | DateTime | Last update |

---

### Rating Calculation

**Formula:**
```
average_rating = (5×five_star + 4×four_star + 3×three_star + 2×two_star + 1×one_star) / total_reviews
```

**Example:**
- 5 stars: 80 reviews
- 4 stars: 30 reviews
- 3 stars: 10 reviews
- 2 stars: 3 reviews
- 1 star: 2 reviews
- **Total:** 125 reviews
- **Average:** (5×80 + 4×30 + 3×10 + 2×3 + 1×2) / 125 = 4.50

---

### Rating Distribution

**Method:** `get_rating_distribution()`
**File:** `apps/profiles/models.py:311-327`

**Returns:**
```json
{
  "5": 64,
  "4": 24,
  "3": 8,
  "2": 2,
  "1": 2
}
```

**Format:** Percentage distribution of ratings

---

### Formatted Review Count

**Method:** `get_formatted_total_reviews()`
**File:** `apps/profiles/models.py:302-309`

**Examples:**
- 472 → "472"
- 1,234 → "1.2K"
- 1,234,567 → "1.2M"

**Purpose:** Display-friendly formatting for large numbers

---

### ProviderReview Model

**File:** `apps/profiles/models.py`

| Field | Type | Description |
|-------|------|-------------|
| provider | ForeignKey(UserProfile) | Provider being reviewed |
| seeker | ForeignKey(UserProfile) | Seeker who reviewed |
| rating | Integer | 1-5 stars |
| review_text | TextField | Optional review text |
| is_verified | Boolean | Verified review |
| review_date | DateTime | Review timestamp |

---

### Rating Flow

```
┌──────────────────────────────────────────┐
│ 1. SERVICE COMPLETED                     │
│    - Provider marks service as finished  │
│    - Seeker receives notification        │
│    - Rating prompt shown to seeker       │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 2. SEEKER SUBMITS RATING                 │
│    - Selects 1-5 stars (required)        │
│    - Writes review text (optional)       │
│    - Submits via app                     │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 3. CREATE REVIEW RECORD                  │
│    - Creates ProviderReview              │
│    - Links to provider and seeker        │
│    - Stores in WorkSession               │
│    - Sets is_verified = true             │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 4. UPDATE AGGREGATED RATING              │
│    - Increments star count               │
│    - Increments total_reviews            │
│    - Recalculates average_rating         │
│    - Updates ProviderRating              │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 5. DISPLAY TO SEEKERS                    │
│    - Average rating shown in search      │
│    - Star distribution visible           │
│    - Recent reviews displayed            │
│    - Provider profile updated            │
└──────────────────────────────────────────┘
```

---

### Rating Storage in WorkSession

**File:** `apps/profiles/work_assignment_models.py`

| Field | Description |
|-------|-------------|
| rating_stars | 1-5 stars given by seeker |
| rating_description | Review text |
| rated_at | Rating timestamp |

**Note:** Only seekers can rate providers after work completion

---

### Rating Display

**In Provider Profile:**
- Average rating (e.g., 4.50/5.00)
- Total review count (e.g., "125" or "1.2K")
- Star distribution chart
- Recent reviews with text

**In Search Results:**
- Average rating badge
- Total review count
- Quick star display

---

## 8. Referral System

### Overview

**Code:** Each provider's `provider_id` is their referral code
**Rewards:** ₹100 for referrer, ₹50 for referee
**Limit:** Each provider can use only ONE referral code
**Auto-Credit:** Rewards automatically credited to wallets

**Documentation:** `apps/referrals/README.md`

---

### ProviderReferral Model

**File:** `apps/referrals/models.py`

| Field | Type | Description |
|-------|------|-------------|
| referred_provider | OneToOne(UserProfile) | New provider |
| referrer_provider | ForeignKey(UserProfile) | Existing provider |
| referral_code_used | CharField(10) | Provider ID used |
| status | CharField | pending/completed/cancelled |
| created_at | DateTime | Referral creation |
| completed_at | DateTime | Completion timestamp |

**Constraint:** OneToOne on referred_provider ensures one referral per provider

---

### ReferralReward Model

**File:** `apps/referrals/models.py`

| Field | Type | Description |
|-------|------|-------------|
| referral | ForeignKey(ProviderReferral) | Parent referral |
| provider | ForeignKey(UserProfile) | Reward recipient |
| reward_type | CharField | referrer/referee |
| amount | Decimal(10,2) | Reward amount |
| currency | CharField | Default: INR |
| is_credited | Boolean | Credited to wallet? |
| created_at | DateTime | Reward creation |
| credited_at | DateTime | Credit timestamp |

---

### Referral Flow

```
┌──────────────────────────────────────────┐
│ 1. NEW PROVIDER SIGNS UP                 │
│    - Completes profile setup             │
│    - Gets provider_id: AB87654321        │
│    - Can now use referral code           │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 2. APPLIES REFERRAL CODE                 │
│    - Enters referrer's provider_id       │
│    - POST /api/1/referral/               │
│    - Body: {"referral_code": "AB12345678"}│
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 3. VALIDATION                            │
│    - Code is valid provider_id? ✓        │
│    - Not self-referral? ✓                │
│    - Haven't used code before? ✓         │
│    - Referrer wallet exists? ✓           │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 4. CREATE REFERRAL RECORD                │
│    - Creates ProviderReferral            │
│    - referred_provider = new provider    │
│    - referrer_provider = existing        │
│    - status = completed                  │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 5. CREATE REWARD RECORDS                 │
│    - ReferralReward #1:                  │
│      • provider = referrer               │
│      • reward_type = referrer            │
│      • amount = ₹100                     │
│    - ReferralReward #2:                  │
│      • provider = referee                │
│      • reward_type = referee             │
│      • amount = ₹50                      │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 6. CREDIT TO WALLETS                     │
│    - Referrer wallet: +₹100              │
│    - Referee wallet: +₹50                │
│    - Creates WalletTransactions          │
│    - Sets is_credited = true             │
│    - Sets credited_at = now()            │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 7. CONFIRMATION                          │
│    - Returns success message             │
│    - Shows new balances                  │
│    - Both providers notified             │
└──────────────────────────────────────────┘
```

---

### Validation Rules

**✓ Valid Referral:**
- Code is existing provider_id
- Not user's own provider_id
- User hasn't used any referral code before
- Referrer is active provider

**✗ Invalid Referral:**
- Non-existent provider_id
- Self-referral attempt
- Already used a referral code
- Referrer account suspended/deleted

---

### Referral Statistics API

**Endpoint:** `GET /api/1/referral/`

**Response:**
```json
{
  "referralCode": "AB12345678",
  "referralCount": 5,
  "totalEarned": 500.0,
  "currency": "INR",
  "rewardPerReferral": 100.0,
  "stats": {
    "totalReferrals": 5,
    "pendingReferrals": 0,
    "completedReferrals": 5
  },
  "recentReferrals": [
    {
      "friendName": "John Doe",
      "status": "completed",
      "rewardAmount": 100.0,
      "referredAt": "2025-10-10T14:30:00Z",
      "completedAt": "2025-10-10T14:30:00Z"
    }
  ]
}
```

---

### Referral Sharing

**Provider Can Share:**
- Their provider_id directly
- Via QR code (future)
- Via share link (future)

**Where to Share:**
- Social media
- WhatsApp/Telegram
- In-person (show provider_id)
- Marketing materials

---

## 9. Verification System

### Overview

**Purpose:** Verify provider identity and credentials
**Types:** Aadhaar, Driving/Commercial License
**Optional:** Can skip initially, required for certain services

---

### AadhaarVerification Model

**File:** `apps/verification/models.py`

| Field | Type | Description |
|-------|------|-------------|
| user | OneToOne(UserProfile) | Owner |
| aadhaar_number | CharField(12) | 12-digit Aadhaar |
| status | CharField | pending/verified/failed/skipped |
| otp_sent_at | DateTime | OTP send time |
| verified_at | DateTime | Verification time |
| can_skip | Boolean | Can skip? (default True) |

**Validation:**
- Exactly 12 digits
- Numeric only
- Unique per user
- Validator: `validate_aadhaar_number()` (Line 24)

---

### Aadhaar Verification Flow

```
┌──────────────────────────────────────────┐
│ 1. PROVIDER ENTERS AADHAAR               │
│    - Enters 12-digit Aadhaar number      │
│    - Validates format                    │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 2. SEND OTP                              │
│    - Creates AadhaarVerification         │
│    - status = pending                    │
│    - Sends OTP to registered mobile      │
│    - Sets otp_sent_at timestamp          │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 3. VERIFY OTP                            │
│    - Provider enters OTP                 │
│    - Validates against Aadhaar service   │
│    - status = verified                   │
│    - Sets verified_at timestamp          │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 4. VERIFICATION COMPLETE                 │
│    - Provider profile updated            │
│    - Aadhaar badge shown                 │
│    - Higher trust for seekers            │
└──────────────────────────────────────────┘

┌──────────────────────────────────────────┐
│ ALTERNATIVE: SKIP VERIFICATION           │
│    - Provider clicks "Skip"              │
│    - status = skipped                    │
│    - Can verify later                    │
└──────────────────────────────────────────┘
```

---

### LicenseVerification Model

**File:** `apps/verification/models.py`

| Field | Type | Description |
|-------|------|-------------|
| user | OneToOne(UserProfile) | Owner |
| license_number | CharField(50) | License number |
| license_type | CharField | driving/commercial/other |
| status | CharField | pending/verified/failed |
| is_required | Boolean | Required for drivers |
| verified_at | DateTime | Verification time |

**License Types:**
- `driving` - Standard driving license (default)
- `commercial` - Commercial vehicle license
- `other` - Other license types

**Required For:**
- Providers with service_type = 'driver'
- Optional for others

---

### License Verification Flow

```
┌──────────────────────────────────────────┐
│ 1. PROVIDER UPLOADS LICENSE              │
│    - Enters license number               │
│    - Selects license type                │
│    - Uploads photo (front/back)          │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 2. MANUAL REVIEW (Admin)                 │
│    - Admin views uploaded documents      │
│    - Verifies authenticity               │
│    - Checks expiry date                  │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│ 3. APPROVAL/REJECTION                    │
│    Option A: APPROVED                    │
│    - status = verified                   │
│    - Sets verified_at timestamp          │
│    - Provider notified                   │
│                                          │
│    Option B: REJECTED                    │
│    - status = failed                     │
│    - Reason provided                     │
│    - Provider can resubmit               │
└──────────────────────────────────────────┘
```

---

### Verification Benefits

**For Verified Providers:**
- ✅ Verified badge on profile
- ✅ Higher search ranking
- ✅ Increased seeker trust
- ✅ Access to premium features (future)
- ✅ Better job opportunities

**For Seekers:**
- ✅ Confidence in provider identity
- ✅ Safer transactions
- ✅ Reduced fraud risk
- ✅ Can filter by verified providers

---

### Verification Status Display

**In Provider Profile:**
```json
{
  "verification": {
    "aadhaar_verified": true,
    "license_verified": false
  }
}
```

**In Search Results:**
- Verified badge icon
- "Aadhaar Verified" tag
- "License Verified" tag

---

## 10. Admin Features

### Django Admin Interface

**URL:** `/admin/`
**Access:** Superuser accounts only

---

### UserProfile Admin

**File:** `apps/profiles/admin/profile_admin.py`

**Features:**
- Profile photo preview
- Status actions (activate/deactivate)
- Profile completion checker
- Bulk actions

**List Display:**
- Full name
- Mobile number
- User type
- Service type
- Profile complete status
- Created date

**Filters:**
- User type (provider/seeker)
- Service type
- Profile complete
- Gender
- Created date range

**Search:**
- Full name
- Mobile number
- Provider ID

**Actions:**
- Mark as profile complete
- Mark as profile incomplete
- Activate for work
- Deactivate for work

---

### Work Order Admin

**File:** `apps/profiles/admin/work_assignment_admin.py`

**List Display:**
- Seeker name
- Provider name
- Category
- Status
- Assigned date

**Filters:**
- Status
- Category
- Date range

**Search:**
- Seeker name
- Provider name
- Description

---

### Wallet Admin

**File:** `apps/profiles/admin/profile_admin.py`

**List Display:**
- User name
- Balance
- Currency
- Subscription status

**Filters:**
- Subscription active
- Balance range

**Actions:**
- Add credit
- Deduct amount
- Activate subscription

---

### Referral Admin

**File:** `apps/referrals/admin.py`

**List Display:**
- Referred provider
- Referrer provider
- Referral code
- Status
- Created date

**Filters:**
- Status
- Created date

**Search:**
- Provider names
- Referral code

**Actions:**
- Mark as completed
- Cancel referral
- Credit rewards

---

### Notification Admin

**List Display:**
- User
- Notification type
- Delivery method
- Delivery status
- Sent date

**Filters:**
- Notification type
- Delivery method
- Delivery status
- Date range

---

### Statistics Dashboard (Future)

**Planned Features:**
- Total users (seekers/providers)
- Active work orders
- Completed services
- Revenue metrics
- User growth charts
- Popular categories
- Average ratings
- Referral statistics

---

## End of Part 3

**Related Documents:**
- **Part 1:** VISIBLE_OVERVIEW_AND_ARCHITECTURE.md (Overview and Database)
- **Part 2:** VISIBLE_API_ENDPOINTS_AND_FLOWS.md (API Endpoints and User Flows)

---

## Summary

### WebSocket Endpoints
- `ws/location/{user_type}/` - Location tracking
- `ws/work/provider/` - Provider work assignment & chat
- `ws/work/seeker/` - Seeker work assignment & chat

### Key Features
- Real-time location tracking with Haversine distance calculation
- Work assignment with FCM + WebSocket dual delivery
- Anonymous chat with 24-hour auto-expiration
- Message delivery and read receipts
- Typing indicators and user presence
- Wallet with ₹20/24hr online subscription
- Rating & review system (seeker → provider)
- Referral rewards (₹100 + ₹50 auto-credit)
- Aadhaar and License verification
- Comprehensive Django admin interface

### Message Types (15+)
- work_assigned, work_response, work_accepted, work_rejected
- medium_share, seeker_medium_selection
- location_update, distance_update
- start_chat, chat_message
- message_delivered, message_read
- typing_indicator, user_presence
- cancel_connection, finish_service

### Notification Types (5)
- work_assigned, work_accepted, work_rejected
- work_completed, work_cancelled

### Transaction Types (2)
- credit - Money added (referrals, refunds)
- debit - Money deducted (subscription, fees)

---

**Document Version:** 1.0
**Created:** October 23, 2025
**Last Updated:** October 30, 2025
**Total WebSocket Messages:** 15+
**Total Notification Types:** 5
**Real-Time Features:** Location tracking, Chat, Presence

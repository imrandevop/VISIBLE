# VISIBLE - Complete Project Documentation
# Part 2: API Endpoints and User Flows

**Version:** 1.0
**Last Updated:** October 23, 2025

---

## Table of Contents - Part 2

1. [API Overview](#api-overview)
2. [Authentication APIs](#authentication-apis)
3. [Profile APIs](#profile-apis)
4. [Work Category APIs](#work-category-apis)
5. [Location APIs](#location-apis)
6. [Referral APIs](#referral-apis)
7. [Complete User Flows](#complete-user-flows)
8. [Work Order Lifecycle](#work-order-lifecycle)
9. [Role Switching Flow](#role-switching-flow)

---

## 1. API Overview

### Base URL
- **Production:** `https://api.visibleapp.in`
- **Staging:** `https://workflow-z7zt.onrender.com`
- **Local:** `http://localhost:8000`

### API Version
All endpoints are prefixed with `/api/1/`

### Authentication
Most endpoints require JWT Bearer token:
```
Authorization: Bearer <access_token>
```

### Response Format
All responses follow this structure:
```json
{
  "status": "success" | "error",
  "message": "Human-readable message",
  "data": { ... },
  "errors": { ... }  // Only for validation errors
}
```

### HTTP Status Codes
- `200` - Success
- `201` - Created
- `400` - Bad Request (validation errors)
- `401` - Unauthorized (missing/invalid token)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found
- `500` - Internal Server Error

---

## 2. Authentication APIs

**Base Path:** `/api/1/authentication/`
**File:** `apps/authentication/urls.py`

### 2.1 Send OTP

**Endpoint:** `POST /api/1/authentication/send-otp/`
**Authentication:** Not required
**File:** `apps/authentication/views.py`

**Request Body:**
```json
{
  "mobile_number": "9876543210"
}
```

**Validation:**
- Must be exactly 10 digits
- Only numeric characters allowed

**Response (Success - 200):**
```json
{
  "status": "success",
  "message": "OTP sent successfully to 9876543210",
  "data": {
    "mobile_number": "9876543210",
    "otp_sent_at": "2025-10-23T10:30:00Z"
  }
}
```

**Current Implementation:**
- Dummy OTP: "123456" for all users (development mode)
- Ready for SMS gateway integration

---

### 2.2 Verify OTP

**Endpoint:** `POST /api/1/authentication/verify-otp/`
**Authentication:** Not required
**File:** `apps/authentication/views.py`

**Request Body:**
```json
{
  "mobile_number": "9876543210",
  "otp": "123456"
}
```

**Response - New User (200):**
```json
{
  "status": "success",
  "message": "OTP verified successfully",
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "data": {
    "user_id": 123,
    "mobile_number": "9876543210",
    "is_mobile_verified": true,
    "is_new_user": true,
    "profile_complete": false,
    "can_access_app": false,
    "user_type": null,
    "next_action": "complete_profile"
  }
}
```

**Response - Existing User (200):**
```json
{
  "status": "success",
  "message": "Login successful",
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "data": {
    "user_id": 123,
    "mobile_number": "9876543210",
    "is_mobile_verified": true,
    "is_new_user": false,
    "profile_complete": true,
    "can_access_app": true,
    "user_type": "provider",
    "service_type": "worker",
    "provider_id": "AB12345678",
    "full_name": "John Doe",
    "profile_photo": "https://.../photo.jpg",
    "next_action": "access_dashboard"
  }
}
```

**JWT Token Details:**
- **Access Token Lifetime:** 7 days
- **Refresh Token Lifetime:** 30 days
- **Algorithm:** HS256
- **Claims:** user_id, mobile_number, is_mobile_verified, user_type

**Process:**
1. Validates OTP (currently accepts "123456")
2. Creates or retrieves User by mobile_number
3. Sets is_mobile_verified = true
4. Checks if UserProfile exists
5. Generates JWT tokens
6. Returns profile status and next action

---

### 2.3 Refresh Token

**Endpoint:** `POST /api/1/authentication/refresh-token/`
**Authentication:** Not required

**Request Body:**
```json
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Response (200):**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Use Case:**
- When access token expires (after 7 days)
- Client should automatically refresh before expiry

---

### 2.4 Delete Account

**Endpoint:** `DELETE /api/1/authentication/delete-account/`
**Authentication:** Required (Bearer token)

**Request Body:** None

**Response (200):**
```json
{
  "status": "success",
  "message": "Account deleted successfully"
}
```

**Note:** This is a soft delete - data retained for recovery

---

## 3. Profile APIs

**Base Path:** `/api/1/profiles/`
**File:** `apps/profiles/urls.py`

### 3.1 Seeker Profile Setup

**Endpoint:** `POST /api/1/profiles/seeker/setup/`
**Authentication:** Required
**File:** `apps/profiles/views/profile_views.py`
**Serializer:** `SeekerProfileSetupSerializer`

**Request Body (Individual Seeker):**
```json
{
  "full_name": "John Doe",
  "date_of_birth": "1990-05-15",
  "gender": "male",
  "profile_photo": "<file_upload_or_url>",
  "languages": ["English", "Hindi"]
}
```

**Request Body (Business Seeker):**
```json
{
  "seeker_type": "business",
  "full_name": "John Doe",
  "date_of_birth": "1990-05-15",
  "gender": "male",
  "profile_photo": "<file_upload_or_url>",
  "languages": ["English", "Hindi"],
  "business_name": "Doe Enterprises",
  "business_location": "123 Business Street, City",
  "established_date": "2015-06-20",
  "website": "https://www.doeenterprises.com"
}
```

**Required Fields for Business Seekers:**
- `seeker_type` - Set to "business"
- `business_name` - Business name (required)
- `business_location` - Business address (required)
- `established_date` - Date business was established (required)
- `website` - Business website (optional)

**Response (200) - Individual Seeker:**
```json
{
  "status": "success",
  "message": "Seeker profile setup completed successfully",
  "profile": {
    "id": 123,
    "full_name": "John Doe",
    "user_type": "seeker",
    "seeker_type": "individual",
    "gender": "male",
    "date_of_birth": "1990-05-15",
    "age": 35,
    "profile_photo": "https://.../photo.jpg",
    "languages": ["English", "Hindi"],
    "profile_complete": true,
    "can_access_app": true,
    "mobile_number": "9876543210",
    "created_at": "2025-10-30T10:30:00Z",
    "updated_at": "2025-10-30T10:30:00Z"
  }
}
```

**Response (200) - Business Seeker:**
```json
{
  "status": "success",
  "message": "Seeker profile setup completed successfully",
  "profile": {
    "id": 124,
    "full_name": "John Doe",
    "user_type": "seeker",
    "seeker_type": "business",
    "gender": "male",
    "date_of_birth": "1990-05-15",
    "age": 35,
    "profile_photo": "https://.../photo.jpg",
    "languages": ["English", "Hindi"],
    "business_name": "Doe Enterprises",
    "business_location": "123 Business Street, City",
    "established_date": "2015-06-20",
    "website": "https://www.doeenterprises.com",
    "profile_complete": true,
    "can_access_app": true,
    "mobile_number": "9876543210",
    "created_at": "2025-10-30T10:30:00Z",
    "updated_at": "2025-10-30T10:30:00Z"
  }
}
```

---

### 3.2 Provider Profile Setup

**Endpoint:** `POST /api/1/profiles/provider/setup/`
**Authentication:** Required
**File:** `apps/profiles/views/profile_views.py`
**Serializer:** `ProviderProfileSetupSerializer`

**Request Body:**
```json
{
  "full_name": "Jane Smith",
  "date_of_birth": "1988-08-20",
  "gender": "female",
  "profile_photo": "<file_upload_or_url>",
  "languages": ["English", "Hindi"],
  "service_type": "skill",
  "service_coverage_area": 25,
  "main_category_id": "MS0001",
  "sub_category_ids": ["SS0001", "SS0002", "SS0003"],
  "years_experience": 5,
  "skills": "Expert in plumbing work with 5 years experience",
  "portfolio_images": [
    "<file_upload_or_url>",
    "<file_upload_or_url>"
  ]
}
```

**Required Fields for All Providers:**
- `service_type` - skill/vehicle/properties/SOS
- `service_coverage_area` - Service coverage radius in kilometers (required)
- `main_category_id` - Main service category code (e.g., "MS0001")
- `sub_category_ids` - Array of subcategory codes (e.g., ["SS0001", "SS0002"])
- `portfolio_images` - 1 to 3 images (minimum 1 recommended)

**Service-Specific Additional Fields:**

**For Vehicle (service_type=vehicle):**
```json
{
  "service_type": "vehicle",
  "service_coverage_area": 30,
  "main_category_id": "MS0002",
  "sub_category_ids": ["SS0010", "SS0011"],
  "years_experience": 5,
  "vehicle_types": ["Car", "SUV"],
  "license_number": "DL1234567890",
  "vehicle_registration_number": "DL01AB1234",
  "driving_experience_description": "5 years professional driving experience",
  "vehicle_service_offering_types": ["rent", "lease"]
}
```

**Required Fields for Vehicle Providers:**
- `vehicle_types` - Array of vehicle types
- `license_number` - Driving license number
- `vehicle_registration_number` - Vehicle registration number
- `years_experience` - Years of driving experience
- `driving_experience_description` - Description of experience
- `vehicle_service_offering_types` - Array: ["rent", "sale", "lease", "all"]

**For Properties (service_type=properties):**
```json
{
  "service_type": "properties",
  "service_coverage_area": 15,
  "main_category_id": "MS0003",
  "sub_category_ids": ["SS0020"],
  "years_experience": 3,
  "property_types": ["Apartment", "Villa"],
  "property_title": "Luxury 3BHK Apartment",
  "property_description": "Spacious apartment with modern amenities",
  "parking_availability": "Yes",
  "furnishing_type": "Fully Furnished",
  "property_service_offering_types": ["rent", "sale"]
}
```

**Required Fields for Property Providers:**
- `property_types` - Array of property types
- `property_title` - Property title
- `property_description` - Description of the property
- `property_service_offering_types` - Array: ["rent", "sale", "lease", "all"]
- `parking_availability` - Optional: "Yes" or "No"
- `furnishing_type` - Optional: "Fully Furnished", "Semi Furnished", "Unfurnished"

**For SOS (service_type=SOS):**
```json
{
  "service_type": "SOS",
  "service_coverage_area": 50,
  "main_category_id": "MS0004",
  "sub_category_ids": ["SS0030"],
  "years_experience": 10,
  "skills": "Emergency medical services provider",
  "emergency_service_types": ["Medical Emergency", "Ambulance"],
  "contact_number": "9876543210",
  "current_location": "Delhi NCR",
  "emergency_description": "24/7 emergency medical services available"
}
```

**Required Fields for SOS Providers:**
- `emergency_service_types` - Array of emergency service types
- `contact_number` - Emergency contact number
- `current_location` - Current service location
- `emergency_description` - Description of emergency services

**Response (200):**
```json
{
  "status": "success",
  "message": "Provider profile setup completed successfully",
  "profile": {
    "id": 124,
    "full_name": "Jane Smith",
    "user_type": "provider",
    "service_type": "skill",
    "gender": "female",
    "date_of_birth": "1988-08-20",
    "age": 37,
    "profile_photo": "https://.../photo.jpg",
    "languages": ["English", "Hindi"],
    "service_coverage_area": 25,
    "provider_id": "AB87654321",
    "profile_complete": true,
    "can_access_app": true,
    "mobile_number": "9876543210",
    "portfolio_images": [
      "https://.../portfolio1.jpg",
      "https://.../portfolio2.jpg"
    ],
    "service_data": {
      "main_category_id": "MS0001",
      "main_category_name": "Plumber",
      "sub_category_ids": ["SS0001", "SS0002", "SS0003"],
      "sub_category_names": ["Pipe Fitting", "Leak Repair", "Bathroom Installation"],
      "years_experience": 5,
      "skills": "Expert in plumbing work with 5 years experience"
    },
    "created_at": "2025-10-30T10:35:00Z",
    "updated_at": "2025-10-30T10:35:00Z"
  }
}
```

**Auto-Generated on Provider Setup:**
1. `provider_id` - Format: AB######## (2 letters + 8 digits)
2. `Wallet` - Balance 0.00 INR (via signal)
3. Service-specific data based on service_type
4. UserWorkSelection records (for worker type)

**Validation:**
- Portfolio images: 1-3 required, max 2MB each
- Image formats: jpg, jpeg, png
- Date of birth: Must be at least 18 years old
- Profile photo: Optional but recommended

---

### 3.1.1 Separated Profile Setup Endpoints (New)

**NEW:** As of October 2025, we've introduced separated endpoints for better code maintainability and clearer API structure. These endpoints provide the same functionality as the unified `/setup/` endpoint but are specifically tailored for seeker and provider profiles.

#### Seeker Profile Setup

**Endpoint:** `POST /api/1/profiles/seeker/setup/`
**Authentication:** Required
**File:** `apps/profiles/views/profile_views.py`
**Serializer:** `apps/profiles/serializers/profile_serializers.py` - `SeekerProfileSetupSerializer`

**Request Body (Individual Seeker):**
```json
{
  "full_name": "John Doe",
  "date_of_birth": "1990-05-15",
  "gender": "male",
  "profile_photo": "<file_upload_or_url>",
  "languages": ["English", "Hindi"]
}
```

**Request Body (Business Seeker):**
```json
{
  "seeker_type": "business",
  "full_name": "John Doe",
  "date_of_birth": "1990-05-15",
  "gender": "male",
  "profile_photo": "<file_upload_or_url>",
  "languages": ["English", "Hindi"],
  "business_name": "Doe Enterprises",
  "business_location": "123 Business Street, City",
  "established_date": "2015-06-20",
  "website": "https://www.doeenterprises.com"
}
```

**Key Differences from Unified Endpoint:**
- No need to specify `user_type` - automatically set to "seeker"
- Clearer validation errors specific to seeker profiles
- Only seeker-related fields are accepted

**Response (200):**
```json
{
  "status": "success",
  "message": "Seeker profile setup completed successfully",
  "profile": {
    "id": 123,
    "full_name": "John Doe",
    "user_type": "seeker",
    "seeker_type": "individual",
    "gender": "male",
    "date_of_birth": "1990-05-15",
    "profile_photo": "https://.../photo.jpg",
    "languages": ["English", "Hindi"],
    "profile_complete": true,
    "can_access_app": true,
    "mobile_number": "9876543210",
    "created_at": "2025-10-30T10:30:00Z",
    "updated_at": "2025-10-30T10:30:00Z"
  }
}
```

#### Provider Profile Setup

**Endpoint:** `POST /api/1/profiles/provider/setup/`
**Authentication:** Required
**File:** `apps/profiles/views/profile_views.py`
**Serializer:** `apps/profiles/serializers/profile_serializers.py` - `ProviderProfileSetupSerializer`

**Request Body (Skill Provider):**
```json
{
  "full_name": "Jane Smith",
  "date_of_birth": "1988-08-20",
  "gender": "female",
  "profile_photo": "<file_upload_or_url>",
  "languages": ["English", "Hindi"],
  "service_type": "skill",
  "service_coverage_area": 25,
  "main_category_id": "MS0001",
  "sub_category_ids": ["SS0001", "SS0002"],
  "years_experience": 5,
  "skills": "Expert in plumbing work",
  "portfolio_images": ["<file1>", "<file2>"]
}
```

**Key Differences from Unified Endpoint:**
- No need to specify `user_type` - automatically set to "provider"
- Clearer validation errors specific to provider profiles
- Only provider-related fields are accepted
- Better error messages for service-specific validations

**Response (200):**
```json
{
  "status": "success",
  "message": "Provider profile setup completed successfully",
  "profile": {
    "id": 124,
    "full_name": "Jane Smith",
    "user_type": "provider",
    "service_type": "skill",
    "gender": "female",
    "date_of_birth": "1988-08-20",
    "profile_photo": "https://.../photo.jpg",
    "languages": ["English", "Hindi"],
    "service_coverage_area": 25,
    "provider_id": "AB87654321",
    "profile_complete": true,
    "can_access_app": true,
    "service_data": {
      "main_category_id": "MS0001",
      "main_category_name": "Plumber",
      "sub_category_ids": ["SS0001", "SS0002"],
      "sub_category_names": ["Pipe Fitting", "Leak Repair"],
      "years_experience": 5,
      "skills": "Expert in plumbing work"
    },
    "portfolio_images": [
      "https://.../portfolio1.jpg",
      "https://.../portfolio2.jpg"
    ],
    "mobile_number": "9876543210",
    "created_at": "2025-10-30T10:30:00Z",
    "updated_at": "2025-10-30T10:30:00Z"
  }
}
```

#### Migration Guide

**For Mobile/Frontend Developers:**

**Option 1: Immediate Migration (Recommended)**
Update your app to use the new separated endpoints based on user type selection:

```dart
// Old code
final response = await http.post(
  'https://api.visibleapp.in/api/1/profiles/setup/',
  body: {
    'user_type': userType,  // 'seeker' or 'provider'
    ...otherFields
  }
);

// New code
final endpoint = userType == 'seeker'
  ? 'https://api.visibleapp.in/api/1/profiles/seeker/setup/'
  : 'https://api.visibleapp.in/api/1/profiles/provider/setup/';

final response = await http.post(
  endpoint,
  body: {
    // No need to send user_type
    ...otherFields
  }
);
```

**Option 2: No Changes Required**
The original unified endpoint `/api/1/profiles/setup/` is still available and fully functional. You can continue using it without any code changes.

**Benefits of Migration:**
1. ✅ **Clearer Errors** - Validation errors are more specific and easier to debug
2. ✅ **Better Documentation** - Each endpoint has focused documentation
3. ✅ **Type Safety** - No risk of sending provider fields to seeker endpoint
4. ✅ **Future Proof** - Easier to add new features specific to each user type
5. ✅ **Better Performance** - Smaller serializers mean faster validation

**Backward Compatibility:**
- The unified `/api/1/profiles/setup/` endpoint remains fully supported
- All existing mobile apps will continue to work without any changes
- No breaking changes to response structure
- Same authentication and validation rules apply

**When to Use Which Endpoint:**

| Scenario | Recommended Endpoint |
|----------|---------------------|
| New app development | Use separated endpoints (`/seeker/setup/` or `/provider/setup/`) |
| Existing app (can update) | Migrate to separated endpoints for better maintainability |
| Existing app (cannot update immediately) | Continue using unified `/setup/` endpoint |
| Backend/Admin tools | Use separated endpoints for clarity |

**Important Notes:**
- Profile updates work the same way - just POST with updated fields
- Both create and update operations use the same endpoint (no separate PUT/PATCH)
- The `user_type` field is automatically set and cannot be changed via these endpoints
- For role switching (seeker ↔ provider), use the `/switch-role/` endpoint

---

### 3.2 Get Profile

**Endpoint:** `GET /api/1/profiles/me/`
**Authentication:** Required
**File:** `apps/profiles/views/profile_views.py`

**Response (200):**
```json
{
  "status": "success",
  "data": {
    "id": 124,
    "full_name": "Jane Smith",
    "date_of_birth": "1988-08-20",
    "gender": "female",
    "profile_photo": "https://.../photo.jpg",
    "user_type": "provider",
    "service_type": "skill",
    "service_coverage_area": 25,
    "provider_id": "AB87654321",
    "seeker_type": null,
    "business_name": null,
    "business_location": null,
    "established_date": null,
    "website": null,
    "profile_complete": true,
    "can_access_app": true,
    "mobile_number": "9876543210",
    "is_active_for_work": false,
    "fcm_token": "fcm_token_here",
    "wallet": {
      "balance": "250.00",
      "currency": "INR",
      "is_online_subscription_active": false,
      "online_subscription_expires_at": null
    },
    "rating": {
      "average_rating": "4.50",
      "total_reviews": 125,
      "five_star_count": 80,
      "four_star_count": 30,
      "three_star_count": 10,
      "two_star_count": 3,
      "one_star_count": 2
    },
    "main_category": {
      "id": 1,
      "name": "Plumber",
      "code": "MS0001"
    },
    "sub_categories": [
      {"id": 1, "name": "Pipe Fitting", "code": "SS0001"}
    ],
    "portfolio_images": [
      {
        "id": 1,
        "image": "https://.../portfolio1.jpg",
        "caption": "Work sample 1"
      }
    ],
    "service_data": {
      "license_number": "DL1234567890",
      "vehicle_type": "car"
    },
    "verification": {
      "aadhaar_verified": false,
      "license_verified": false
    },
    "communication_settings": {
      "whatsapp": "9876543210",
      "call": "9876543210",
      "telegram": "@username"
    },
    "role_switch_history": {
      "previous_user_type": "seeker",
      "role_switch_count": 2,
      "last_role_switch_date": "2025-10-20T14:22:00Z"
    },
    "created_at": "2025-10-23T10:30:00Z",
    "updated_at": "2025-10-23T15:45:00Z"
  }
}
```

**Returns Complete Profile Including:**
- Basic profile information
- Wallet details with subscription status
- Rating and review statistics
- Service categories and portfolio
- Service-specific data
- Verification status
- Communication settings
- Role switch history

---

### 3.3 Get Profile Status

**Endpoint:** `GET /api/1/profiles/status/`
**Authentication:** Required
**File:** `apps/profiles/views/profile_views.py`

**Response (200):**
```json
{
  "status": "success",
  "data": {
    "profile_complete": true,
    "can_access_app": true,
    "user_type": "provider",
    "service_type": "worker",
    "provider_id": "AB87654321",
    "next_action": "access_dashboard",
    "main_category": {
      "id": 1,
      "name": "Plumber"
    },
    "is_active_for_work": false
  }
}
```

**Use Case:**
- Check if user needs to complete profile
- Determine which screen to show (setup vs dashboard)
- Quick status check without full profile data

**Next Action Values:**
- `complete_profile` - User needs to setup profile
- `access_dashboard` - User can access main app

---

### 3.4 Update FCM Token

**Endpoint:** `POST /api/1/profiles/update-fcm-token/`
**Authentication:** Required

**Request Body:**
```json
{
  "fcm_token": "firebase_cloud_messaging_token_here"
}
```

**Response (200):**
```json
{
  "status": "success",
  "message": "FCM token updated successfully"
}
```

**Use Case:**
- Register device for push notifications
- Update token when it changes (Firebase refresh)
- Required for receiving work assignment notifications

---

### 3.5 Update Communication Settings

**Endpoint:** `POST /api/1/profiles/communication/`
**Authentication:** Required

**Request Body:**
```json
{
  "telegram": "@username",
  "whatsapp": "9876543210",
  "call": "9876543210",
  "map_location": "https://maps.google.com/?q=28.7041,77.1025",
  "website": "https://example.com",
  "instagram": "https://instagram.com/username",
  "facebook": "https://facebook.com/username",
  "land_mark": "Near City Hospital, Main Road",
  "upi_ID": "user@upi"
}
```

**All fields are optional** - provide only the mediums you want to share

**Response (200):**
```json
{
  "status": "success",
  "message": "Communication settings updated successfully",
  "data": {
    "telegram": "@username",
    "whatsapp": "9876543210",
    "call": "9876543210"
  }
}
```

**Use Case:**
- Provider shares contact methods with seekers
- Seeker can choose which medium to use
- Shared during work sessions

---

### 3.6 Get Wallet

**Endpoint:** `GET /api/1/profiles/wallet/`
**Authentication:** Required
**File:** `apps/profiles/views/wallet_views.py`

**Response (200):**
```json
{
  "status": "success",
  "data": {
    "balance": "250.00",
    "currency": "INR",
    "is_online_subscription_active": true,
    "online_subscription_expires_at": "2025-10-24T14:30:00Z",
    "last_online_payment_at": "2025-10-23T14:30:00Z",
    "recent_transactions": [
      {
        "id": 45,
        "transaction_type": "debit",
        "amount": "20.00",
        "description": "24-hour online subscription charge",
        "balance_after": "230.00",
        "created_at": "2025-10-23T14:30:00Z"
      },
      {
        "id": 44,
        "transaction_type": "credit",
        "amount": "100.00",
        "description": "Referral reward for referring provider John Doe",
        "balance_after": "250.00",
        "created_at": "2025-10-22T10:15:00Z"
      }
    ]
  }
}
```

**Auto-Creates Wallet:**
- If wallet doesn't exist, creates one with 0.00 balance
- Seamless for users switching to provider role

---

### 3.7 Provider Dashboard

**Endpoint:** `GET /api/1/profiles/provider/dashboard/`
**Authentication:** Required (user_type must be provider)
**File:** `apps/profiles/views/dashboard_views.py`

**Response (200):**
```json
{
  "status": "success",
  "data": {
    "profile_complete": true,
    "is_active_for_work": false,
    "provider_id": "AB87654321",
    "wallet": {
      "balance": "250.00",
      "currency": "INR",
      "is_online_subscription_active": false
    },
    "rating": {
      "average_rating": "4.50",
      "total_reviews": "125",
      "formatted_reviews": "125"
    },
    "services": {
      "main_category": "Plumber",
      "sub_categories": ["Pipe Fitting", "Leak Repair"],
      "service_type": "worker"
    },
    "active_work_orders": [
      {
        "id": 234,
        "seeker_name": "John Client",
        "category": "Plumber",
        "status": "accepted",
        "assigned_at": "2025-10-23T14:00:00Z"
      }
    ],
    "offers": [],
    "previous_services": [
      {
        "id": 233,
        "seeker_name": "Jane Customer",
        "category": "Plumber",
        "status": "completed",
        "rating": 5,
        "completed_at": "2025-10-22T16:30:00Z"
      }
    ],
    "aadhaar_verified": false,
    "license_verified": false,
    "maintenance_mode": false
  }
}
```

**Includes:**
- Profile and online status
- Wallet and subscription details
- Rating statistics
- Active work orders (pending, accepted)
- Previous completed services
- Verification status
- System maintenance status

---

### 3.8 Seeker Dashboard

**Endpoint:** `GET /api/1/profiles/seeker/dashboard/`
**Authentication:** Required (user_type must be seeker)
**File:** `apps/profiles/views/dashboard_views.py`

**Response (200):**
```json
{
  "status": "success",
  "data": {
    "profile_complete": true,
    "is_searching": false,
    "wallet": {
      "balance": "50.00",
      "currency": "INR"
    },
    "active_work_orders": [
      {
        "id": 234,
        "provider_name": "Jane Smith",
        "provider_id": "AB87654321",
        "category": "Plumber",
        "status": "accepted",
        "assigned_at": "2025-10-23T14:00:00Z"
      }
    ],
    "offers": [],
    "previous_services": [
      {
        "id": 232,
        "provider_name": "Mike Worker",
        "category": "Electrician",
        "status": "completed",
        "your_rating": 4,
        "completed_at": "2025-10-21T18:00:00Z"
      }
    ],
    "maintenance_mode": false
  }
}
```

**Includes:**
- Profile and search status
- Wallet balance
- Active work orders (pending, accepted, in_progress)
- Previous completed services with ratings
- System maintenance status

---

### 3.9 Switch Role

**Endpoint:** `POST /api/1/profiles/switch-role/`
**Authentication:** Required
**File:** `apps/profiles/views/wallet_views.py`
**Serializer:** `apps/profiles/serializers/role_switch_serializers.py`
**Documentation:** `ROLE_SWITCH_API.md`

**Request Body:**
```json
{
  "new_user_type": "provider"
}
```

**Validation Rules:**
- No active work orders (any status except completed/rejected/cancelled)
- Provider must be offline (is_active_for_work = false)
- No recent wallet transactions (within 5 minutes)
- Cannot switch to same role

**Response (200):**
```json
{
  "status": "success",
  "message": "Role switched successfully from seeker to provider",
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "data": {
    "id": 123,
    "full_name": "John Doe",
    "user_type": "provider",
    "service_type": "worker",
    "provider_id": "AB12345678",
    "profile_complete": false,
    "can_access_app": true,
    "mobile_number": "9876543210",
    "created_at": "2025-01-15T10:30:00Z",
    "updated_at": "2025-10-23T14:22:00Z"
  }
}
```

**CRITICAL: New JWT Tokens Returned**
- Old tokens contain old user_type (immutable)
- Must replace old tokens with new ones
- New tokens contain updated user_type claim

**Process:**
1. Validates role switch eligibility
2. Updates user_type, previous_user_type, role_switch_count
3. Sets is_active_for_work = false (go offline)
4. Creates RoleSwitchHistory record
5. Ensures Wallet exists
6. Generates new JWT tokens with updated user_type
7. Adjusts profile_complete based on direction:
   - Seeker → Provider: profile_complete = false (need provider setup)
   - Provider → Seeker: profile_complete = true (basic info sufficient)
8. Sets can_access_app = true (preserve access)

**Error Response - Active Work Orders (400):**
```json
{
  "status": "error",
  "message": "You have active work orders as a seeker. Please complete or cancel them before switching roles.",
  "errors": {
    "error": ["You have active work orders as a seeker..."]
  }
}
```

**Error Response - Provider Online (400):**
```json
{
  "status": "error",
  "message": "Please go offline before switching roles.",
  "errors": {
    "error": ["Please go offline before switching roles."]
  }
}
```

---

## 4. Work Category APIs

**Base Path:** `/api/1/work-categories/`
**File:** `apps/work_categories/urls.py`

### 4.1 List Main Categories

**Endpoint:** `GET /api/1/work-categories/`
**Authentication:** Required

**Response (200):**
```json
{
  "status": "success",
  "data": [
    {
      "id": 1,
      "category_code": "MS0001",
      "name": "Plumber",
      "display_name": "Plumber",
      "description": "Plumbing and pipe fitting services",
      "icon_url": "https://.../plumber-icon.png",
      "is_active": true,
      "sort_order": 1
    },
    {
      "id": 2,
      "category_code": "MS0002",
      "name": "Electrician",
      "display_name": "Electrician",
      "description": "Electrical wiring and repair services",
      "icon_url": "https://.../electrician-icon.png",
      "is_active": true,
      "sort_order": 2
    }
  ]
}
```

**Main Category Examples:**
- Plumber (MS0001)
- Electrician (MS0002)
- Carpenter (MS0003)
- Painter (MS0004)
- Driver (MS0005)
- Real Estate (MS0006)
- Emergency Services (MS0007)

---

### 4.2 List Subcategories

**Endpoint:** `GET /api/1/work-categories/{category_id}/subcategories/`
**Authentication:** Required

**Response (200):**
```json
{
  "status": "success",
  "data": [
    {
      "id": 1,
      "sub_category_code": "SS0001",
      "name": "Pipe Fitting",
      "display_name": "Pipe Fitting",
      "description": "Installation and repair of water pipes",
      "icon_url": "https://.../pipe-icon.png",
      "is_active": true,
      "sort_order": 1,
      "category": 1
    },
    {
      "id": 2,
      "sub_category_code": "SS0002",
      "name": "Leak Repair",
      "display_name": "Leak Repair",
      "description": "Fixing water leaks and drips",
      "icon_url": "https://.../leak-icon.png",
      "is_active": true,
      "sort_order": 2,
      "category": 1
    }
  ]
}
```

---

### 4.3 Get Category Details

**Endpoint:** `GET /api/1/work-categories/{category_id}/`
**Authentication:** Required

**Response (200):**
```json
{
  "status": "success",
  "data": {
    "id": 1,
    "category_code": "MS0001",
    "name": "Plumber",
    "display_name": "Plumber",
    "description": "Plumbing and pipe fitting services",
    "icon_url": "https://.../plumber-icon.png",
    "is_active": true,
    "sort_order": 1,
    "subcategories": [
      {
        "id": 1,
        "sub_category_code": "SS0001",
        "name": "Pipe Fitting"
      },
      {
        "id": 2,
        "sub_category_code": "SS0002",
        "name": "Leak Repair"
      }
    ]
  }
}
```

---

## 5. Location APIs

**Base Path:** `/api/1/location/`
**File:** `apps/location_services/urls.py`

### 5.1 Toggle Provider Online Status

**Endpoint:** `POST /api/1/location/provider/toggle/`
**Authentication:** Required (user_type must be provider)

**Request Body:**
```json
{
  "is_active": true,
  "latitude": 28.7041,
  "longitude": 77.1025,
  "main_category_id": 1,
  "sub_category_id": 1
}
```

**Response - Going Online (200):**
```json
{
  "status": "success",
  "message": "Provider is now online",
  "data": {
    "is_active": true,
    "latitude": 28.7041,
    "longitude": 77.1025,
    "main_category": "Plumber",
    "sub_category": "Pipe Fitting",
    "last_active_at": "2025-10-23T15:00:00Z"
  }
}
```

**Response - Going Offline (200):**
```json
{
  "status": "success",
  "message": "Provider is now offline",
  "data": {
    "is_active": false,
    "last_active_at": "2025-10-23T15:30:00Z"
  }
}
```

**Use Case:**
- Provider toggles availability for work
- Updates location for seeker matching
- Specifies active service category

---

### 5.2 Toggle Seeker Search Status

**Endpoint:** `POST /api/1/location/seeker/toggle/`
**Authentication:** Required (user_type must be seeker)

**Request Body:**
```json
{
  "is_searching": true,
  "latitude": 28.7041,
  "longitude": 77.1025,
  "searching_category_id": 1,
  "searching_subcategory_id": 1,
  "distance_radius": 5
}
```

**Response (200):**
```json
{
  "status": "success",
  "message": "Search started successfully",
  "data": {
    "is_searching": true,
    "latitude": 28.7041,
    "longitude": 77.1025,
    "searching_category": "Plumber",
    "searching_subcategory": "Pipe Fitting",
    "distance_radius": 5,
    "last_search_at": "2025-10-23T15:00:00Z"
  }
}
```

**Distance Radius:**
- Default: 5 km
- Can be customized by seeker
- Used for provider matching

**Provider Filtering Logic:**
Providers are shown to seekers only if:
1. Provider is within seeker's search radius (distance_radius)
2. **AND** Seeker is within provider's service coverage area (service_coverage_area)

This ensures that only providers who can actually service the seeker's location are displayed.

---

## 6. Referral APIs

**Base Path:** `/api/1/referral/`
**File:** `apps/referrals/urls.py`
**Documentation:** `apps/referrals/README.md`

### 6.1 Apply Referral Code

**Endpoint:** `POST /api/1/referral/`
**Authentication:** Required (user_type must be provider)

**Request Body:**
```json
{
  "referral_code": "AB12345678"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Referral code applied successfully! You earned ₹50 and your referrer earned ₹100",
  "data": {
    "referrer_reward": 100.00,
    "referee_reward": 50.00,
    "your_new_balance": 50.00
  }
}
```

**Process:**
1. Validates referral code (must be valid provider_id)
2. Checks not self-referral
3. Checks not already used referral code
4. Creates ProviderReferral record
5. Creates 2 ReferralReward records
6. Credits ₹100 to referrer's wallet
7. Credits ₹50 to referee's wallet
8. Creates 2 WalletTransaction records

**Error - Invalid Code (400):**
```json
{
  "success": false,
  "message": "Validation failed",
  "errors": {
    "referral_code": ["Invalid referral code. Please check and try again."]
  }
}
```

**Error - Self Referral (400):**
```json
{
  "success": false,
  "message": "Validation failed",
  "errors": {
    "non_field_errors": ["You cannot use your own referral code."]
  }
}
```

**Error - Already Used (400):**
```json
{
  "success": false,
  "message": "Validation failed",
  "errors": {
    "non_field_errors": ["You have already used a referral code. Each provider can only use one referral code."]
  }
}
```

---

### 6.2 Get Referral Statistics

**Endpoint:** `GET /api/1/referral/`
**Authentication:** Required (user_type must be provider)

**Response (200):**
```json
{
  "success": true,
  "message": "Referral data retrieved successfully",
  "data": {
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
      },
      {
        "friendName": "Jane Smith",
        "status": "completed",
        "rewardAmount": 100.0,
        "referredAt": "2025-10-15T10:20:00Z",
        "completedAt": "2025-10-15T10:20:00Z"
      }
    ]
  }
}
```

**Use Case:**
- Provider can share their provider_id as referral code
- Track referral earnings
- View referral history

---

## 7. Complete User Flows

### 7.1 New Seeker Registration & First Use

```
STEP 1: Authentication
┌─────────────────────────────────────────┐
│ POST /api/1/authentication/send-otp/    │
│ Body: {"mobile_number": "9876543210"}   │
│ Response: OTP sent (dummy: 123456)      │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│ POST /api/1/authentication/verify-otp/  │
│ Body: {"mobile_number": "...",          │
│        "otp": "123456"}                  │
│ Response: JWT tokens, is_new_user=true, │
│           next_action="complete_profile" │
└─────────────────────────────────────────┘

STEP 2: Profile Setup
┌─────────────────────────────────────────┐
│ POST /api/1/profiles/setup/             │
│ Headers: Authorization: Bearer <token>  │
│ Body: {                                 │
│   "full_name": "John Doe",              │
│   "date_of_birth": "1990-05-15",        │
│   "gender": "male"                      │
│ }                                       │
│ Response: profile_complete=true         │
│           can_access_app=true           │
│           user_type="seeker"            │
└─────────────────────────────────────────┘
                  ↓
STEP 3: Access Dashboard
┌─────────────────────────────────────────┐
│ GET /api/1/profiles/seeker/dashboard/   │
│ Headers: Authorization: Bearer <token>  │
│ Response: Dashboard data                │
└─────────────────────────────────────────┘
                  ↓
STEP 4: Search for Provider (via WebSocket)
┌─────────────────────────────────────────┐
│ POST /api/1/location/seeker/toggle/     │
│ Body: {                                 │
│   "is_searching": true,                 │
│   "latitude": 28.7041,                  │
│   "longitude": 77.1025,                 │
│   "searching_category_id": 1,           │
│   "distance_radius": 5                  │
│ }                                       │
└─────────────────────────────────────────┘
                  ↓
STEP 5: Connect to Work WebSocket
┌─────────────────────────────────────────┐
│ ws://api/1/ws/work/seeker/              │
│ Headers: Authorization: Bearer <token>  │
│ (See Part 3 for WebSocket details)     │
└─────────────────────────────────────────┘
```

---

### 7.2 New Provider Registration & First Use

```
STEP 1: Authentication (Same as Seeker)
┌─────────────────────────────────────────┐
│ POST /api/1/authentication/send-otp/    │
│ POST /api/1/authentication/verify-otp/  │
│ Response: JWT tokens, is_new_user=true  │
└─────────────────────────────────────────┘

STEP 2: Provider Profile Setup
┌─────────────────────────────────────────┐
│ POST /api/1/profiles/setup/             │
│ Body: {                                 │
│   "full_name": "Jane Smith",            │
│   "date_of_birth": "1988-08-20",        │
│   "gender": "female",                   │
│   "service_type": "worker",             │
│   "main_category_id": 1,                │
│   "sub_category_ids": [1, 2, 3],        │
│   "portfolio_images": [...]             │
│ }                                       │
│ Response: provider_id="AB87654321"      │
│           wallet created                │
│           profile_complete=true         │
└─────────────────────────────────────────┘

STEP 3: Apply Referral Code (Optional)
┌─────────────────────────────────────────┐
│ POST /api/1/referral/                   │
│ Body: {"referral_code": "AB12345678"}   │
│ Response: ₹50 credited to wallet        │
│           Referrer gets ₹100            │
└─────────────────────────────────────────┘

STEP 4: Access Provider Dashboard
┌─────────────────────────────────────────┐
│ GET /api/1/profiles/provider/dashboard/ │
│ Response: Dashboard with wallet, rating │
└─────────────────────────────────────────┘

STEP 5: Go Online
┌─────────────────────────────────────────┐
│ POST /api/1/location/provider/toggle/   │
│ Body: {                                 │
│   "is_active": true,                    │
│   "latitude": 28.7041,                  │
│   "longitude": 77.1025,                 │
│   "main_category_id": 1                 │
│ }                                       │
└─────────────────────────────────────────┘

STEP 6: Connect to Work WebSocket
┌─────────────────────────────────────────┐
│ ws://api/1/ws/work/provider/            │
│ Wait for work assignments via FCM       │
│ (See Part 3 for WebSocket details)     │
└─────────────────────────────────────────┘
```

---

### 7.3 Existing User Login

```
STEP 1: Authentication
┌─────────────────────────────────────────┐
│ POST /api/1/authentication/send-otp/    │
│ POST /api/1/authentication/verify-otp/  │
│ Response: JWT tokens, is_new_user=false │
│           profile data included         │
│           next_action="access_dashboard"│
└─────────────────────────────────────────┘

STEP 2: Check Profile Status (Optional)
┌─────────────────────────────────────────┐
│ GET /api/1/profiles/status/             │
│ Response: profile_complete, user_type   │
└─────────────────────────────────────────┘

STEP 3: Access Dashboard
┌─────────────────────────────────────────┐
│ GET /api/1/profiles/provider/dashboard/ │
│          OR                             │
│ GET /api/1/profiles/seeker/dashboard/   │
└─────────────────────────────────────────┘

STEP 4: Resume Activity
- Provider: Go online, connect to WebSocket
- Seeker: Start searching, connect to WebSocket
```

---

## 8. Work Order Lifecycle

### Complete Work Order Flow

```
┌────────────────────────────────────────────────────────────┐
│                    SEEKER INITIATES                         │
└────────────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────┐
│ 1. WORK ASSIGNMENT                                          │
│    - Seeker selects provider from search results            │
│    - Creates WorkOrder (status: pending)                    │
│    - Sends FCM notification to provider                     │
│    - Sends WebSocket message to provider                    │
│                                                             │
│    WebSocket Event:                                         │
│    {                                                        │
│      "type": "work_assigned",                               │
│      "work_order_id": 234,                                  │
│      "seeker_name": "John Client",                          │
│      "category": "Plumber",                                 │
│      "description": "Fix kitchen sink leak",                │
│      "distance": "2.5 km"                                   │
│    }                                                        │
└────────────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────┐
│ 2. PROVIDER RESPONSE                                        │
│                                                             │
│    Option A: ACCEPT                                         │
│    - Provider sends work_response (accepted: true)          │
│    - WorkOrder status: pending → accepted                   │
│    - Creates WorkSession                                    │
│    - Notifies seeker via FCM + WebSocket                    │
│                                                             │
│    Option B: REJECT                                         │
│    - Provider sends work_response (accepted: false)         │
│    - WorkOrder status: pending → rejected                   │
│    - Notifies seeker via FCM + WebSocket                    │
│    - Flow ends                                              │
└────────────────────────────────────────────────────────────┘
                          ↓ (if accepted)
┌────────────────────────────────────────────────────────────┐
│ 3. WORK SESSION ACTIVE                                      │
│    - Provider shares communication mediums                  │
│    - Seeker selects preferred mediums                       │
│    - Both can send real-time location updates               │
│    - Anonymous chat active                                  │
│    - Distance tracking between seeker and provider          │
│                                                             │
│    Chat Message Format:                                     │
│    {                                                        │
│      "type": "chat_message",                                │
│      "message": "I'm on my way",                            │
│      "sender": "provider"                                   │
│    }                                                        │
└────────────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────┐
│ 4. SERVICE COMPLETION                                       │
│    - Provider marks service as finished                     │
│    - WorkOrder status: accepted → completed                 │
│    - WorkSession state: active → completed                  │
│    - Notifies seeker for rating                             │
│    - Chat messages set to expire in 24 hours                │
└────────────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────┐
│ 5. RATING & REVIEW (Seeker Only)                            │
│    - Seeker rates provider (1-5 stars)                      │
│    - Optional review text                                   │
│    - Updates ProviderRating aggregate                       │
│    - Creates ProviderReview record                          │
│                                                             │
│    Rating Stored in WorkSession:                            │
│    - rating_stars: 5                                        │
│    - rating_description: "Excellent work!"                  │
│    - rated_at: timestamp                                    │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│                  CANCELLATION FLOW                          │
│                                                             │
│ Can Cancel From:                                            │
│ - pending → cancelled (before acceptance)                   │
│ - accepted → cancelled (after acceptance)                   │
│                                                             │
│ Who Can Cancel:                                             │
│ - Seeker: Any time before completion                        │
│ - Provider: After acceptance, before completion             │
│                                                             │
│ On Cancellation:                                            │
│ - WorkOrder status → cancelled                              │
│ - WorkSession state → cancelled                             │
│ - Notifies both parties                                     │
│ - Chat messages expire in 24 hours                          │
└────────────────────────────────────────────────────────────┘
```

---

### Work Order Status Transitions

```
[pending]
    │
    ├──→ [accepted] ──→ [completed]
    │        │
    │        └──→ [cancelled]
    │
    ├──→ [rejected]
    │
    └──→ [cancelled]
```

**Status Details:**

| Status | Description | Can Transition To |
|--------|-------------|-------------------|
| pending | Work assigned, awaiting provider response | accepted, rejected, cancelled |
| accepted | Provider accepted work | completed, cancelled |
| rejected | Provider rejected work | (terminal state) |
| completed | Work finished and rated | (terminal state) |
| cancelled | Work cancelled by either party | (terminal state) |

---

## 9. Role Switching Flow

### Detailed Role Switch Process

```
┌────────────────────────────────────────────────────────────┐
│ PREREQUISITE CHECKS                                         │
│                                                             │
│ ✓ No active work orders (any role)                         │
│ ✓ Provider is offline (is_active_for_work = false)         │
│ ✓ No recent wallet transactions (5 min window)             │
│ ✓ Valid target role (provider ↔ seeker)                    │
└────────────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────┐
│ SWITCH DIRECTION: SEEKER → PROVIDER                         │
│                                                             │
│ Request:                                                    │
│ POST /api/1/profiles/switch-role/                          │
│ {"new_user_type": "provider"}                              │
│                                                             │
│ Process:                                                    │
│ 1. Update UserProfile:                                      │
│    - previous_user_type = "seeker"                          │
│    - user_type = "provider"                                 │
│    - role_switch_count += 1                                 │
│    - last_role_switch_date = now()                          │
│    - profile_complete = false (need provider setup)         │
│    - can_access_app = true (preserve access)                │
│    - is_active_for_work = false                             │
│                                                             │
│ 2. Create RoleSwitchHistory record                          │
│                                                             │
│ 3. Ensure Wallet exists (create if missing)                 │
│                                                             │
│ 4. Generate NEW JWT tokens with user_type="provider"        │
│                                                             │
│ Response:                                                   │
│ - New access_token                                          │
│ - New refresh_token                                         │
│ - Updated profile data                                      │
│                                                             │
│ Next Steps:                                                 │
│ - User needs to complete provider profile setup             │
│ - Select service_type, categories, upload portfolio         │
│ - After setup: profile_complete = true                      │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ SWITCH DIRECTION: PROVIDER → SEEKER                         │
│                                                             │
│ Request:                                                    │
│ POST /api/1/profiles/switch-role/                          │
│ {"new_user_type": "seeker"}                                │
│                                                             │
│ Process:                                                    │
│ 1. Update UserProfile:                                      │
│    - previous_user_type = "provider"                        │
│    - user_type = "seeker"                                   │
│    - role_switch_count += 1                                 │
│    - last_role_switch_date = now()                          │
│    - profile_complete = true (basic info sufficient)        │
│    - can_access_app = true                                  │
│    - is_active_for_work = false                             │
│    - service_type PRESERVED (for switching back)            │
│    - provider_id PRESERVED                                  │
│                                                             │
│ 2. Create RoleSwitchHistory record                          │
│                                                             │
│ 3. Generate NEW JWT tokens with user_type="seeker"          │
│                                                             │
│ Response:                                                   │
│ - New access_token                                          │
│ - New refresh_token                                         │
│ - Updated profile data                                      │
│                                                             │
│ Next Steps:                                                 │
│ - User can immediately access seeker dashboard              │
│ - All provider data preserved for future switch back        │
└────────────────────────────────────────────────────────────┘
```

---

### Data Preservation During Role Switch

**Preserved When Switching:**
- ✅ provider_id (kept for switching back)
- ✅ service_type (worker/driver/properties/SOS)
- ✅ Wallet balance and transactions
- ✅ Rating and review data
- ✅ Work history (as provider and seeker)
- ✅ Service-specific data (DriverServiceData, etc.)
- ✅ Portfolio images
- ✅ Communication settings
- ✅ Verification status (Aadhaar, License)

**Reset When Switching:**
- ❌ is_active_for_work → false (go offline)
- ❌ JWT tokens → new tokens generated

**Adjusted When Switching:**
- profile_complete:
  - Seeker → Provider: false (need provider setup)
  - Provider → Seeker: true (basic info sufficient)

---

### Role Switch Client Implementation

**Frontend Must:**
1. ✅ Call switch-role API
2. ✅ Receive new JWT tokens in response
3. ✅ **REPLACE old tokens with new tokens immediately**
4. ✅ Update app state with new user_type
5. ✅ Navigate to appropriate screen:
   - Seeker → Provider: Profile setup (if not complete)
   - Provider → Seeker: Dashboard

**Critical: Token Replacement**
```javascript
// After successful role switch
const result = await switchRole('provider');
if (result.status === 'success') {
  // MUST replace tokens
  localStorage.setItem('access_token', result.access_token);
  localStorage.setItem('refresh_token', result.refresh_token);

  // Update app state
  setUserType(result.data.user_type);

  // Navigate based on profile_complete
  if (!result.data.profile_complete) {
    navigate('/profile-setup');
  } else {
    navigate('/dashboard');
  }
}
```

---

## End of Part 2

**Continue to:**
- **Part 1:** VISIBLE_OVERVIEW_AND_ARCHITECTURE.md (Overview and Database)
- **Part 3:** VISIBLE_WEBSOCKET_AND_FEATURES.md (WebSocket and Features)

---

**Document Version:** 1.0
**Created:** October 23, 2025
**Total Endpoints:** 20+
**Authentication:** JWT Bearer Tokens
**API Version:** v1

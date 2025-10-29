# VISIBLE - Complete Project Documentation
# Part 1: Overview and Architecture

**Version:** 1.0
**Last Updated:** October 23, 2025
**Django Version:** 5.2.5
**Python Version:** 3.x

---

## Table of Contents - Part 1

1. [Project Overview](#project-overview)
2. [Technology Stack](#technology-stack)
3. [Project Structure](#project-structure)
4. [Django Apps Architecture](#django-apps-architecture)
5. [Database Schema](#database-schema)
6. [Models Reference](#models-reference)
7. [Settings and Configuration](#settings-and-configuration)

---

## 1. Project Overview

### What is VISIBLE?

VISIBLE is a **mobile-first service marketplace platform** that connects service seekers with service providers in real-time. The platform supports multiple service categories including workers, drivers, property services, and emergency (SOS) services.

### Key Features

- **OTP-Based Authentication** with JWT tokens
- **Dual User Roles** - Seeker and Provider with role-switching capability
- **Real-Time Location Tracking** using WebSocket connections
- **Work Assignment System** with FCM push notifications
- **Anonymous Chat** between seeker and provider during work sessions
- **Wallet System** with ₹20/24-hour online subscription for providers
- **Rating & Review System** (Seeker rates Provider)
- **Referral Program** (₹100 for referrer, ₹50 for referee)
- **Identity Verification** (Aadhaar and License)
- **Communication Mediums** (8 channels: Telegram, WhatsApp, Call, etc.)
- **Service Portfolio** (Up to 3 images per provider)

### Platform Statistics

- **30+ Models** across 7 Django apps
- **20+ API Endpoints** (REST + WebSocket)
- **3 WebSocket Consumers** for real-time features
- **10,000+ Lines of Code**
- **Supported Service Types:** Worker, Driver, Properties, SOS

---

## 2. Technology Stack

### Backend Framework
- **Django 5.2.5** - Main web framework
- **Django REST Framework 3.16.1** - API framework
- **Django Channels 4.0.0** - WebSocket support
- **REST Framework SimpleJWT** - JWT authentication

### Database
- **PostgreSQL** (Production)
- **SQLite** (Development)

### Real-Time & Messaging
- **Django Channels** - WebSocket protocol
- **Redis** - Channel layers (with InMemory fallback)
- **Firebase Cloud Messaging (FCM)** - Push notifications

### External Services
- **Firebase Admin SDK 6.5.0** - FCM integration
- **OTP Service** (Placeholder - currently dummy "123456")

### Additional Libraries
- **Pillow** - Image processing
- **Psycopg2** - PostgreSQL adapter
- **Gunicorn** - WSGI HTTP Server
- **WhiteNoise** - Static file serving
- **python-decouple** - Environment configuration
- **dj-database-url** - Database URL parsing

### Deployment
- **Allowed Hosts:** api.visibleapp.in, workflow-z7zt.onrender.com
- **ASGI Application** for WebSocket support
- **Static Files:** WhiteNoise middleware
- **Media Files:** 2MB max, jpg/jpeg/png formats

---

## 3. Project Structure

```
VISIBLE/
│
├── VISIBLE/                          # Project configuration
│   ├── settings.py                   # Main settings (282 lines)
│   ├── urls.py                       # Root URL configuration
│   ├── asgi.py                       # ASGI config with WebSocket routing
│   └── wsgi.py                       # WSGI config
│
├── apps/                             # Django applications
│   ├── authentication/               # User authentication
│   │   ├── models.py                 # Custom User model
│   │   ├── views.py                  # OTP, JWT, account APIs
│   │   ├── urls.py                   # Auth endpoints
│   │   ├── middleware.py             # JWT WebSocket middleware
│   │   ├── serializers.py            # Auth serializers
│   │   └── services/
│   │       └── otp_service.py        # OTP generation/validation
│   │
│   ├── core/                         # Core/shared models
│   │   ├── models.py                 # BaseModel, ProviderActiveStatus, SeekerSearchPreference
│   │   └── utils.py                  # Haversine distance calculation
│   │
│   ├── profiles/                     # User profiles & work system
│   │   ├── models.py                 # UserProfile, Wallet, Rating, Review (1500+ lines)
│   │   ├── work_assignment_models.py # WorkOrder, WorkSession, ChatMessage
│   │   ├── routing.py                # WebSocket URL routing
│   │   ├── urls.py                   # Profile endpoints
│   │   ├── signals.py                # Wallet auto-creation
│   │   ├── notification_services.py  # FCM notification service
│   │   ├── consumers/                # WebSocket consumers (refactored)
│   │   │   ├── __init__.py           # Backward compatible exports
│   │   │   ├── provider_work_consumer.py  # Provider WebSocket logic (1,575 lines)
│   │   │   ├── seeker_work_consumer.py    # Seeker WebSocket logic (1,176 lines)
│   │   │   └── consumer_utils.py     # Shared consumer utilities
│   │   ├── serializers/              # Profile serializers (refactored)
│   │   │   ├── __init__.py           # Backward compatible exports
│   │   │   ├── serializer_utils.py   # Custom fields and utilities (277 lines)
│   │   │   ├── profile_serializers.py     # Profile setup serializers (1,042 lines)
│   │   │   ├── wallet_serializers.py      # Wallet serializers (69 lines)
│   │   │   └── role_switch_serializers.py # Role switching serializers (104 lines)
│   │   ├── views/                    # Profile views (refactored)
│   │   │   ├── __init__.py           # Backward compatible exports
│   │   │   ├── profile_views.py      # Profile CRUD operations (466 lines)
│   │   │   ├── dashboard_views.py    # Dashboard endpoints (411 lines)
│   │   │   └── wallet_views.py       # Wallet and role switch (179 lines)
│   │   └── admin/                    # Django admin (refactored)
│   │       ├── __init__.py           # Import all admin classes
│   │       ├── profile_admin.py      # Profile, wallet, rating admin (497 lines)
│   │       └── work_assignment_admin.py   # Work assignment admin (352 lines)
│   │
│   ├── work_categories/              # Service categories
│   │   ├── models.py                 # WorkCategory, WorkSubCategory, UserWorkSelection
│   │   ├── views.py                  # Category APIs
│   │   ├── urls.py                   # Category endpoints
│   │   └── serializers.py            # Category serializers
│   │
│   ├── location_services/            # Location tracking
│   │   ├── routing.py                # Location WebSocket URLs
│   │   ├── views.py                  # Location toggle APIs
│   │   ├── urls.py                   # Location endpoints
│   │   └── consumers/                # Location consumers (refactored)
│   │       ├── __init__.py           # Export LocationConsumer
│   │       └── location_consumer.py  # LocationConsumer WebSocket (908 lines)
│   │
│   ├── verification/                 # Identity verification
│   │   ├── models.py                 # AadhaarVerification, LicenseVerification
│   │   ├── views.py                  # Verification APIs
│   │   └── serializers.py            # Verification serializers
│   │
│   └── referrals/                    # Referral system
│       ├── models.py                 # ProviderReferral, ReferralReward
│       ├── views.py                  # Referral APIs
│       ├── urls.py                   # Referral endpoints
│       ├── serializers.py            # Referral serializers
│       ├── admin.py                  # Admin interface
│       └── README.md                 # Referral documentation
│
├── media/                            # User-uploaded files
│   └── profile_photos/               # Profile images
│       portfolio_images/             # Provider portfolios
│
├── static/                           # Static files
│
├── manage.py                         # Django management script
├── requirements.txt                  # Python dependencies
└── README files                      # Various documentation
    ├── ROLE_SWITCH_API.md           # Role switching guide
    ├── REFACTORING_SUMMARY.md       # Code refactoring summary
    └── apps/referrals/README.md     # Referral system guide
```

---

## 4. Django Apps Architecture

### 4.1 authentication
**Purpose:** User authentication and account management
**File:** `apps/authentication/`

**Key Components:**
- **Custom User Model** - Mobile number as primary identifier
- **OTP Service** - Send and verify OTP (currently dummy "123456")
- **JWT Token Generation** - 7-day access, 30-day refresh tokens
- **Account Deletion** - Soft delete with data retention

**Models:**
- `User` (Custom User Model)

**Key Files:**
- `models.py:7-29` - User model
- `views.py:21-179` - OTP send/verify APIs
- `middleware.py:14-99` - JWT WebSocket authentication
- `utils/jwt_utils.py:32-48` - JWT token creation

---

### 4.2 core
**Purpose:** Shared models and utilities
**File:** `apps/core/`

**Key Components:**
- **BaseModel** - Abstract model with timestamps
- **ProviderActiveStatus** - Tracks provider online status and location
- **SeekerSearchPreference** - Tracks seeker search parameters
- **Distance Calculation** - Haversine formula utility

**Models:**
- `BaseModel` (Abstract)
- `ProviderActiveStatus`
- `SeekerSearchPreference`

**Key Files:**
- `models.py:38-61` - ProviderActiveStatus
- `models.py:64-88` - SeekerSearchPreference
- `models.py:91-114` - calculate_distance() function

---

### 4.3 profiles
**Purpose:** User profiles, work orders, chat, wallet, ratings
**File:** `apps/profiles/`

**Key Components:**
- **UserProfile** - Complete user profile with dual roles
- **Wallet System** - Balance, transactions, online subscription
- **Work Assignment** - WorkOrder, WorkSession, ChatMessage
- **Rating & Review** - ProviderRating, ProviderReview
- **WebSocket Consumers** - Real-time work assignment and chat
- **Communication Settings** - 8 communication channels
- **Service Portfolio** - Up to 3 images per provider

**Models:**
- `UserProfile`
- `DriverServiceData`, `PropertyServiceData`, `SOSServiceData`
- `ServicePortfolioImage`
- `ProviderRating`, `ProviderReview`
- `Wallet`, `WalletTransaction`
- `CommunicationSettings`
- `WorkOrder`, `WorkSession`, `ChatMessage`
- `WorkAssignmentNotification`
- `RoleSwitchHistory`

**Key Files:**
- `models.py` - Core profile models (1500+ lines)
- `work_assignment_models.py` - Work order models
- `consumers/` - WebSocket consumers package (refactored)
  - `provider_work_consumer.py` - Provider WebSocket logic (1,575 lines)
  - `seeker_work_consumer.py` - Seeker WebSocket logic (1,176 lines)
  - `consumer_utils.py` - Shared utilities
- `serializers/` - Serializers package (refactored)
  - `profile_serializers.py` - Profile setup serializers (1,042 lines)
  - `wallet_serializers.py` - Wallet serializers (69 lines)
  - `role_switch_serializers.py` - Role switching (104 lines)
  - `serializer_utils.py` - Custom fields (277 lines)
- `views/` - Views package (refactored)
  - `profile_views.py` - Profile CRUD operations (466 lines)
  - `dashboard_views.py` - Dashboard endpoints (411 lines)
  - `wallet_views.py` - Wallet and role switch (179 lines)
- `admin/` - Admin package (refactored)
  - `profile_admin.py` - Profile, wallet, rating admin (497 lines)
  - `work_assignment_admin.py` - Work assignment admin (352 lines)
- `signals.py` - Wallet auto-creation signal
- `notification_services.py` - FCM push notifications

---

### 4.4 work_categories
**Purpose:** Service categories and subcategories
**File:** `apps/work_categories/`

**Key Components:**
- **WorkCategory** - Main service categories (e.g., Plumber, Electrician)
- **WorkSubCategory** - Subcategories under main categories
- **UserWorkSelection** - Provider's selected work categories
- **Auto-Generated Codes** - MS0001 (main), SS0001 (sub)

**Models:**
- `WorkCategory`
- `WorkSubCategory`
- `UserWorkSelection`
- `UserWorkSubCategory`

**Key Files:**
- `models.py:7-74` - Category models with auto-code generation
- `views.py` - Category listing APIs
- `serializers.py` - Category serializers

**Main Service Types:**
- `worker` - Labor/Worker services
- `driver` - Transportation/Driver services
- `properties` - Real estate/Property services
- `SOS` - Emergency services

---

### 4.5 location_services
**Purpose:** Real-time location tracking
**File:** `apps/location_services/`

**Key Components:**
- **LocationConsumer** - WebSocket consumer for location updates
- **Location Toggle APIs** - Provider/Seeker online/offline status
- **Distance Calculation** - Haversine formula integration

**WebSocket Endpoints:**
- `ws/location/provider/` - Provider location updates
- `ws/location/seeker/` - Seeker location updates

**Key Files:**
- `consumers/` - Location consumers package (refactored)
  - `location_consumer.py` - LocationConsumer WebSocket logic (908 lines)
- `routing.py` - WebSocket URL patterns
- `views.py` - Location toggle APIs

---

### 4.6 verification
**Purpose:** Identity verification for providers
**File:** `apps/verification/`

**Key Components:**
- **Aadhaar Verification** - 12-digit Aadhaar number validation
- **License Verification** - Driving/Commercial license validation
- **OTP Verification** - For Aadhaar validation
- **Skip Option** - Users can skip verification initially

**Models:**
- `AadhaarVerification`
- `LicenseVerification`

**Verification Statuses:**
- `pending` - Awaiting verification
- `verified` - Successfully verified
- `failed` - Verification failed
- `skipped` - User skipped verification (Aadhaar only)

**Key Files:**
- `models.py:8-53` - AadhaarVerification
- `models.py:55-102` - LicenseVerification
- `serializers.py` - Validation logic

---

### 4.7 referrals
**Purpose:** Provider referral reward system
**File:** `apps/referrals/`

**Key Components:**
- **Referral Code** - Each provider_id is a unique referral code
- **Automatic Rewards** - ₹100 (referrer) + ₹50 (referee)
- **Wallet Integration** - Auto-credits to wallets
- **Validation** - Prevents self-referral and duplicates

**Models:**
- `ProviderReferral`
- `ReferralReward`

**Reward Amounts:**
- Referrer (existing provider): ₹100
- Referee (new provider): ₹50

**Key Files:**
- `models.py` - Referral tracking models
- `views.py` - Apply referral, get stats APIs
- `README.md` - Complete referral documentation

---

## 5. Database Schema

### Schema Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        AUTHENTICATION                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 1:1
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          USER PROFILE                           │
│  • Basic Info (name, DOB, gender, photo)                       │
│  • User Type (seeker/provider)                                 │
│  • Service Type (worker/driver/properties/SOS)                 │
│  • Provider ID (auto-generated)                                │
│  • Role Switching (previous_user_type, switch_count)           │
└─────────────────────────────────────────────────────────────────┘
        │                   │                   │
        │ 1:1               │ 1:1               │ 1:1
        ▼                   ▼                   ▼
┌──────────────┐  ┌──────────────────┐  ┌─────────────────┐
│    WALLET    │  │ COMMUNICATION    │  │ VERIFICATION    │
│ • Balance    │  │    SETTINGS      │  │ • Aadhaar       │
│ • Subscription│  │ • 8 channels    │  │ • License       │
└──────────────┘  └──────────────────┘  └─────────────────┘
        │
        │ 1:N
        ▼
┌──────────────────┐
│ WALLET           │
│ TRANSACTIONS     │
│ • Credit/Debit   │
└──────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      SERVICE CATEGORIES                         │
│  WorkCategory (Main) ──1:N──▶ WorkSubCategory (Sub)           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ N:N
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   PROVIDER SERVICE DATA                         │
│  • UserWorkSelection (worker categories)                       │
│  • DriverServiceData (vehicle info)                            │
│  • PropertyServiceData (property details)                      │
│  • SOSServiceData (emergency services)                         │
│  • ServicePortfolioImage (1-3 images)                          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        WORK ASSIGNMENT                          │
│                                                                 │
│  WorkOrder (Assignment) ──1:1──▶ WorkSession (Chat + Rating)  │
│      │                                    │                     │
│      │ 1:N                               │ 1:N                 │
│      ▼                                    ▼                     │
│  WorkAssignmentNotification         ChatMessage                │
│  (FCM + WebSocket)                  (Auto-expire 24h)          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                       RATING & REVIEW                           │
│                                                                 │
│  ProviderRating ◀──1:1── UserProfile                           │
│  (Aggregated stats)                                            │
│       ▲                                                         │
│       │ Updates from                                           │
│       │                                                         │
│  ProviderReview                                                │
│  (Individual reviews)                                          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      REFERRAL SYSTEM                            │
│                                                                 │
│  ProviderReferral ──1:N──▶ ReferralReward                     │
│  (Tracking)                 (₹100 + ₹50)                       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    REAL-TIME STATUS (Core App)                 │
│                                                                 │
│  ProviderActiveStatus ◀──1:1── User                            │
│  (Online, Location, Category)                                  │
│                                                                 │
│  SeekerSearchPreference ◀──1:1── User                          │
│  (Searching, Location, Radius)                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Models Reference

### 6.1 User (authentication.User)
**File:** `apps/authentication/models.py:7-29`

| Field | Type | Description |
|-------|------|-------------|
| mobile_number | CharField(10) | Unique, primary identifier |
| is_mobile_verified | Boolean | Default: False |
| created_at | DateTime | Auto-generated |

**Relationships:**
- 1:1 with UserProfile
- 1:1 with ProviderActiveStatus
- 1:1 with SeekerSearchPreference

**Authentication:**
- Uses JWT tokens (HS256 algorithm)
- Token lifetime: 7 days (access), 30 days (refresh)
- Token claims: user_id, mobile_number, is_mobile_verified, user_type

---

### 6.2 UserProfile (profiles.UserProfile)
**File:** `apps/profiles/models.py:13-190`

**Basic Fields:**

| Field | Type | Description |
|-------|------|-------------|
| user | OneToOne(User) | Primary key reference |
| full_name | CharField(100) | User's full name |
| date_of_birth | Date | Birth date |
| gender | CharField | Choices: male/female/other |
| profile_photo | ImageField | Optional profile picture |

**Role & Service Fields:**

| Field | Type | Description |
|-------|------|-------------|
| user_type | CharField | Choices: provider/seeker |
| service_type | CharField | Choices: worker/driver/properties/SOS |
| provider_id | CharField(10) | Auto-generated (AB########) |
| profile_complete | Boolean | Profile setup completed |
| can_access_app | Boolean | Can access app features |

**Role Switching Fields:**

| Field | Type | Description |
|-------|------|-------------|
| previous_user_type | CharField | Previous role before switch |
| role_switch_count | Integer | Number of role switches |
| last_role_switch_date | DateTime | Last switch timestamp |

**Activity Fields:**

| Field | Type | Description |
|-------|------|-------------|
| fcm_token | TextField | Firebase Cloud Messaging token |
| is_active_for_work | Boolean | Provider online status |
| created_at | DateTime | Account creation |
| updated_at | DateTime | Last update |

**Provider ID Generation Logic (Lines 73-84):**
```
Format: AB######## (2 random letters + 8 digits)
Example: AB12345678
Ensures uniqueness with retry mechanism
```

**Relationships:**
- 1:1 with User
- 1:1 with Wallet (auto-created via signal)
- 1:1 with ProviderRating
- 1:1 with CommunicationSettings
- 1:N with ServicePortfolioImage (max 3)
- 1:N with WorkOrder (as seeker or provider)
- 1:N with ProviderReview (as provider)
- 1:1 with DriverServiceData (if service_type=driver)
- 1:1 with PropertyServiceData (if service_type=properties)
- 1:1 with SOSServiceData (if service_type=SOS)
- N:N with WorkCategory via UserWorkSelection (if service_type=worker)

---

### 6.3 Service-Specific Models

#### 6.3.1 DriverServiceData
**File:** `apps/profiles/models.py:193-207`

| Field | Type | Description |
|-------|------|-------------|
| user | OneToOne(UserProfile) | Primary key |
| license_number | CharField(50) | Driving license number |
| license_expiry | Date | License expiration |
| vehicle_type | CharField | E.g., car, bike, truck |
| vehicle_model | CharField | Vehicle model |
| vehicle_number | CharField | Registration number |
| years_of_experience | Integer | Driving experience |
| is_vehicle_owned | Boolean | Owns vehicle? |

---

#### 6.3.2 PropertyServiceData
**File:** `apps/profiles/models.py:210-235`

| Field | Type | Description |
|-------|------|-------------|
| user | OneToOne(UserProfile) | Primary key |
| property_type | CharField | Choices: residential/commercial/land |
| property_size | Decimal | Size in sq ft/sq m |
| number_of_rooms | Integer | Room count (nullable) |
| furnishing_status | CharField | Choices: furnished/semi/unfurnished |
| parking_available | Boolean | Parking availability |
| location_details | TextField | Property location |

---

#### 6.3.3 SOSServiceData
**File:** `apps/profiles/models.py:238-251`

| Field | Type | Description |
|-------|------|-------------|
| user | OneToOne(UserProfile) | Primary key |
| emergency_service_type | CharField | Service type |
| emergency_contact | CharField | Emergency contact number |
| service_location | TextField | Service coverage area |
| available_24x7 | Boolean | 24/7 availability |

---

#### 6.3.4 ServicePortfolioImage
**File:** `apps/profiles/models.py:254-280`

| Field | Type | Description |
|-------|------|-------------|
| user | ForeignKey(UserProfile) | Owner |
| image | ImageField | Portfolio image (max 2MB) |
| caption | CharField(255) | Optional caption |
| uploaded_at | DateTime | Upload timestamp |

**Constraints:**
- Maximum 3 images per user
- Formats: jpg, jpeg, png
- Max size: 2MB per image

---

### 6.4 Wallet System

#### 6.4.1 Wallet
**File:** `apps/profiles/models.py:355-409`

| Field | Type | Description |
|-------|------|-------------|
| user | OneToOne(UserProfile) | Primary key |
| balance | Decimal(10,2) | Current balance |
| currency | CharField | Default: INR |
| last_online_payment_at | DateTime | Last ₹20 charge time |
| online_subscription_expires_at | DateTime | Subscription expiry |
| created_at | DateTime | Wallet creation |
| updated_at | DateTime | Last update |

**Key Methods:**

**is_online_subscription_active()** (Lines 372-377)
- Returns True if current time < expiration time
- Used to check if provider's 24-hour subscription is active

**deduct_online_charge()** (Lines 379-405)
- Deducts ₹20.00 from balance
- Sets expiration to now() + 24 hours
- Creates WalletTransaction record
- Returns success/failure message

**Online Subscription Details:**
- **Cost:** ₹20.00
- **Duration:** 24 hours
- **Auto-renew:** Manual (provider must activate)
- **Minimum Balance:** ₹20.00 required

---

#### 6.4.2 WalletTransaction
**File:** `apps/profiles/models.py:412-435`

| Field | Type | Description |
|-------|------|-------------|
| wallet | ForeignKey(Wallet) | Parent wallet |
| transaction_type | CharField | Choices: credit/debit |
| amount | Decimal(10,2) | Transaction amount |
| description | TextField | Transaction description |
| balance_after | Decimal(10,2) | Balance after transaction |
| created_at | DateTime | Transaction time |

**Transaction Types:**
- `credit` - Money added to wallet (referral rewards, refunds)
- `debit` - Money deducted (online subscription, service fees)

**Common Descriptions:**
- "24-hour online subscription charge"
- "Referral reward for referring provider [name]"
- "Referral reward for joining with code [code]"

---

### 6.5 Rating & Review System

#### 6.5.1 ProviderRating
**File:** `apps/profiles/models.py:283-327`

| Field | Type | Description |
|-------|------|-------------|
| provider | OneToOne(UserProfile) | Primary key |
| average_rating | Decimal(3,2) | E.g., 4.50 |
| total_reviews | Integer | Review count |
| five_star_count | Integer | 5-star reviews |
| four_star_count | Integer | 4-star reviews |
| three_star_count | Integer | 3-star reviews |
| two_star_count | Integer | 2-star reviews |
| one_star_count | Integer | 1-star reviews |
| updated_at | DateTime | Last update |

**Key Methods:**

**get_formatted_total_reviews()** (Lines 302-309)
- Formats large numbers: 1234 → "1.2K", 1234567 → "1.2M"

**get_rating_distribution()** (Lines 311-327)
- Returns dictionary with percentage distribution of ratings
- Format: `{"5": 60, "4": 25, "3": 10, "2": 3, "1": 2}`

---

#### 6.5.2 ProviderReview
**File:** `apps/profiles/models.py:330-352`

| Field | Type | Description |
|-------|------|-------------|
| provider | ForeignKey(UserProfile) | Provider being reviewed |
| seeker | ForeignKey(UserProfile) | Seeker who reviewed |
| rating | Integer | 1-5 stars |
| review_text | TextField | Optional review text |
| is_verified | Boolean | Verified review |
| review_date | DateTime | Review timestamp |

**Rating Choices:**
- 1 - Very Poor
- 2 - Poor
- 3 - Average
- 4 - Good
- 5 - Excellent

**Note:** Only seekers can rate providers after work completion

---

### 6.6 Work Assignment Models

#### 6.6.1 WorkOrder
**File:** `apps/profiles/work_assignment_models.py:13-130`

| Field | Type | Description |
|-------|------|-------------|
| seeker | ForeignKey(UserProfile) | Service seeker |
| provider | ForeignKey(UserProfile) | Service provider |
| category | ForeignKey(WorkCategory) | Service category |
| subcategory | ForeignKey(WorkSubCategory) | Service subcategory |
| status | CharField | pending/accepted/rejected/completed/cancelled |
| description | TextField | Work description |
| assigned_at | DateTime | Assignment time |
| accepted_at | DateTime | Acceptance time |
| completed_at | DateTime | Completion time |
| cancelled_at | DateTime | Cancellation time |

**Status Flow:**
```
[pending] ──accept──▶ [accepted] ──complete──▶ [completed]
    │                      │
    │                      └──cancel──▶ [cancelled]
    │
    └──reject──▶ [rejected]
    │
    └──cancel──▶ [cancelled]
```

**Default Status:** `pending`

**Unique Constraint:** One active work order per seeker-provider pair

---

#### 6.6.2 WorkSession
**File:** `apps/profiles/work_assignment_models.py:132-243`

| Field | Type | Description |
|-------|------|-------------|
| work_order | OneToOne(WorkOrder) | Parent work order |
| connection_state | CharField | active/cancelled/completed |
| chat_started_at | DateTime | Chat session start |
| provider_mediums | JSONField | Provider communication channels |
| seeker_mediums | JSONField | Seeker selected channels |
| completed_at | DateTime | Session completion |
| completed_by | ForeignKey(User) | Who completed |
| cancelled_at | DateTime | Session cancellation |
| cancelled_by | ForeignKey(User) | Who cancelled |
| rating_stars | Integer | 1-5 rating (nullable) |
| rating_description | TextField | Review text |
| rated_at | DateTime | Rating timestamp |

**Communication Mediums Format (JSON):**
```json
{
  "telegram": "username_or_id",
  "whatsapp": "phone_number",
  "call": "phone_number",
  "map_location": "google_maps_link",
  "website": "website_url",
  "instagram": "profile_link",
  "facebook": "profile_link",
  "land_mark": "address_landmark",
  "upi_ID": "upi_payment_id"
}
```

**Connection States:**
- `active` - Session in progress
- `cancelled` - Session cancelled
- `completed` - Service completed and rated

---

#### 6.6.3 ChatMessage
**File:** `apps/profiles/work_assignment_models.py:246-303`

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

**Delivery Status:**
- `sent` - Message sent
- `delivered` - Message delivered
- `read` - Message read by recipient

**Auto-Expiration Logic (Lines 287-295):**
- Messages expire **24 hours** after session ends
- Trigger: When session state becomes `cancelled` or `completed`
- Calculation: `expires_at = session.completed_at + timedelta(hours=24)`
- Index on `expires_at` for efficient cleanup

---

#### 6.6.4 WorkAssignmentNotification
**File:** `apps/profiles/work_assignment_models.py:83-130`

| Field | Type | Description |
|-------|------|-------------|
| work_order | ForeignKey(WorkOrder) | Related work order |
| user | ForeignKey(User) | Recipient |
| notification_type | CharField | work_assigned/accepted/rejected/completed/cancelled |
| title | CharField | Notification title |
| body | TextField | Notification body |
| delivery_method | CharField | fcm/websocket |
| delivery_status | CharField | pending/sent/delivered/failed |
| sent_at | DateTime | Send timestamp |
| delivered_at | DateTime | Delivery timestamp |

**Notification Types:**
- `work_assigned` - When seeker assigns work to provider
- `work_accepted` - When provider accepts work
- `work_rejected` - When provider rejects work
- `work_completed` - When work is completed
- `work_cancelled` - When work is cancelled

**Delivery Methods:**
- `fcm` - Firebase Cloud Messaging (push notification)
- `websocket` - Real-time WebSocket message

**Key Functions:**
- `send_work_assignment_notification()` (Line 46)
- `send_work_response_notification()` (Line 151)
- `validate_fcm_token()` (Line 235)

---

### 6.7 Communication Settings
**File:** `apps/profiles/models.py:438-476`

| Field | Type | Description |
|-------|------|-------------|
| user | OneToOne(UserProfile) | Primary key |
| telegram | CharField(100) | Telegram username/ID |
| whatsapp | CharField(15) | WhatsApp number |
| call | CharField(15) | Call number |
| map_location | URLField | Google Maps link |
| website | URLField | Website URL |
| instagram | URLField | Instagram profile |
| facebook | URLField | Facebook profile |
| land_mark | CharField(255) | Address/landmark |
| upi_ID | CharField(100) | UPI payment ID |

**All fields are optional (nullable)**

**Valid Communication Types:**
```python
{'telegram', 'whatsapp', 'call', 'map_location', 'website',
 'instagram', 'facebook', 'land_mark', 'upi_ID'}
```

---

### 6.8 Work Categories

#### 6.8.1 WorkCategory
**File:** `apps/work_categories/models.py:7-37`

| Field | Type | Description |
|-------|------|-------------|
| category_code | CharField(10) | Auto-generated MS0001 |
| name | CharField(100) | Unique name |
| display_name | CharField(100) | Display name |
| description | TextField | Category description |
| icon_url | URLField | Category icon |
| is_active | Boolean | Active status |
| sort_order | Integer | Display order |

**Code Generation (Lines 25-33):**
- Format: `MS0001`, `MS0002`, etc.
- Prefix: `MS` (Main Service)
- Incremental 4-digit number
- Auto-generated on save if not provided

---

#### 6.8.2 WorkSubCategory
**File:** `apps/work_categories/models.py:39-74`

| Field | Type | Description |
|-------|------|-------------|
| category | ForeignKey(WorkCategory) | Parent category |
| sub_category_code | CharField(10) | Auto-generated SS0001 |
| name | CharField(100) | Subcategory name |
| display_name | CharField(100) | Display name |
| description | TextField | Description |
| icon_url | URLField | Icon |
| is_active | Boolean | Active status |
| sort_order | Integer | Display order |

**Code Generation:**
- Format: `SS0001`, `SS0002`, etc.
- Prefix: `SS` (Sub Service)
- Incremental 4-digit number

---

### 6.9 Referral System

#### 6.9.1 ProviderReferral
**File:** `apps/referrals/models.py`

| Field | Type | Description |
|-------|------|-------------|
| referred_provider | OneToOne(UserProfile) | New provider |
| referrer_provider | ForeignKey(UserProfile) | Existing provider |
| referral_code_used | CharField(10) | Provider ID used as code |
| status | CharField | pending/completed/cancelled |
| created_at | DateTime | Referral creation |
| completed_at | DateTime | Completion timestamp |

**Status Values:**
- `pending` - Referral created, rewards not yet credited
- `completed` - Referral completed, rewards credited
- `cancelled` - Referral cancelled

**Key Rule:** Each provider can only use ONE referral code (OneToOne relationship)

---

#### 6.9.2 ReferralReward
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

**Reward Amounts:**
- `referrer` - ₹100.00 (existing provider)
- `referee` - ₹50.00 (new provider)

**Automatic Process:**
1. New provider applies referral code
2. System validates code (not self, not duplicate)
3. Creates ProviderReferral record
4. Creates 2 ReferralReward records
5. Credits ₹100 to referrer's wallet
6. Credits ₹50 to referee's wallet
7. Creates 2 WalletTransaction records

---

### 6.10 Verification Models

#### 6.10.1 AadhaarVerification
**File:** `apps/verification/models.py:8-53`

| Field | Type | Description |
|-------|------|-------------|
| user | OneToOne(UserProfile) | Primary key |
| aadhaar_number | CharField(12) | 12-digit Aadhaar number |
| status | CharField | pending/verified/failed/skipped |
| otp_sent_at | DateTime | OTP send time |
| verified_at | DateTime | Verification time |
| can_skip | Boolean | Can skip? (default True) |

**Validation:**
- Must be exactly 12 digits
- Unique per user
- Validator: `validate_aadhaar_number()` (Line 24)

**Status Flow:**
```
[pending] ──verify OTP──▶ [verified]
    │
    └──skip──▶ [skipped]
    │
    └──failed verification──▶ [failed]
```

---

#### 6.10.2 LicenseVerification
**File:** `apps/verification/models.py:55-102`

| Field | Type | Description |
|-------|------|-------------|
| user | OneToOne(UserProfile) | Primary key |
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
- Providers with `service_type = 'driver'`

---

### 6.11 Core Models

#### 6.11.1 ProviderActiveStatus
**File:** `apps/core/models.py:38-61`

| Field | Type | Description |
|-------|------|-------------|
| user | OneToOne(User) | Primary key |
| is_active | Boolean | Provider online? |
| latitude | Float | Current latitude |
| longitude | Float | Current longitude |
| main_category | ForeignKey(WorkCategory) | Active category |
| sub_category | ForeignKey(WorkSubCategory) | Active subcategory |
| last_active_at | DateTime | Last activity (auto-updated) |

**Purpose:**
- Tracks provider real-time availability
- Stores current location for matching
- Links to active service category
- Updated via WebSocket connections

---

#### 6.11.2 SeekerSearchPreference
**File:** `apps/core/models.py:64-88`

| Field | Type | Description |
|-------|------|-------------|
| user | OneToOne(User) | Primary key |
| is_searching | Boolean | Actively searching? |
| latitude | Float | Search location latitude |
| longitude | Float | Search location longitude |
| searching_category | ForeignKey(WorkCategory) | Desired category |
| searching_subcategory | ForeignKey(WorkSubCategory) | Desired subcategory |
| distance_radius | Integer | Search radius (km, default 5) |
| last_search_at | DateTime | Last search (auto-updated) |

**Purpose:**
- Tracks seeker search parameters
- Stores search location
- Defines search radius (default 5 km)
- Updated when seeker searches for providers

---

#### 6.11.3 Distance Calculation
**File:** `apps/core/models.py:91-114`

**Function:** `calculate_distance(lat1, lng1, lat2, lng2)`

**Algorithm:** Haversine Formula
- Calculates great-circle distance between two points
- Earth radius: 6371 km
- Returns distance in kilometers

**Usage:**
```python
from apps.core.models import calculate_distance

distance_km = calculate_distance(
    provider_lat, provider_lng,
    seeker_lat, seeker_lng
)
```

---

### 6.12 RoleSwitchHistory
**File:** `apps/profiles/models.py:479-498`

| Field | Type | Description |
|-------|------|-------------|
| user | ForeignKey(UserProfile) | User who switched |
| from_user_type | CharField | Previous role |
| to_user_type | CharField | New role |
| switch_date | DateTime | Switch timestamp |

**Purpose:**
- Audit trail for role switching
- Track user behavior patterns
- Analyze role switch frequency

**Creates Record When:**
- User switches from seeker to provider
- User switches from provider to seeker

---

## 7. Settings and Configuration

### 7.1 Django Settings
**File:** `VISIBLE/settings.py`

**Key Configurations:**

```python
# Custom User Model
AUTH_USER_MODEL = 'authentication.User'

# Database
- PostgreSQL (Production via DATABASE_URL)
- SQLite (Development fallback)

# Time Zone
TIME_ZONE = 'Asia/Kolkata'
USE_TZ = True

# Static Files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media Files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024  # 2MB

# Allowed Hosts
ALLOWED_HOSTS = [
    'api.visibleapp.in',
    'workflow-z7zt.onrender.com',
    'localhost',
    '127.0.0.1',
    '143.110.178.190'
]

# CSRF Trusted Origins
CSRF_TRUSTED_ORIGINS = [
    'https://api.visibleapp.in',
    'https://workflow-z7zt.onrender.com',
    'http://localhost',
    'http://127.0.0.1'
]
```

---

### 7.2 REST Framework Configuration

```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ],
}
```

---

### 7.3 JWT Configuration

```python
from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=7),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}
```

**Token Claims:**
- `user_id` - User ID
- `mobile_number` - Mobile number
- `is_mobile_verified` - Verification status
- `user_type` - Current user role (seeker/provider)

**Token Generation:** `apps/authentication/utils/jwt_utils.py:32-48`

---

### 7.4 Django Channels Configuration

```python
# ASGI Application
ASGI_APPLICATION = 'VISIBLE.asgi.application'

# Channel Layers
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [os.environ.get('REDIS_URL', 'redis://localhost:6379')],
        },
    },
}

# Fallback to InMemory for development
if not REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer'
        }
    }
```

**WebSocket Routing:** `VISIBLE/asgi.py`

```python
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddlewareStack(
        URLRouter(
            location_patterns + work_patterns
        )
    ),
})
```

---

### 7.5 Firebase Configuration

**Firebase Admin SDK:**
- Used for Firebase Cloud Messaging (FCM)
- Push notifications for work assignments
- Token validation and management

**Integration File:** `apps/profiles/notification_services.py`

**Functions:**
- `send_work_assignment_notification()`
- `validate_fcm_token()`

---

### 7.6 Middleware Stack

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
```

**Custom WebSocket Middleware:**
- `JWTAuthMiddlewareStack` (apps/authentication/middleware.py:14-99)
- Extracts JWT token from WebSocket Authorization header
- Validates token and sets `scope['user']`
- Falls back to AnonymousUser if invalid

---

## End of Part 1

**Continue to:**
- **Part 2:** VISIBLE_API_ENDPOINTS_AND_FLOWS.md (API Endpoints and User Flows)
- **Part 3:** VISIBLE_WEBSOCKET_AND_FEATURES.md (WebSocket and Features)

---

**Document Version:** 1.0
**Created:** October 23, 2025
**Total Models:** 30+
**Total Apps:** 7
**Total Files Documented:** 50+

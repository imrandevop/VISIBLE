# Role Switching API - Documentation

## Overview
Users can switch between Seeker and Provider roles. The API returns **new JWT tokens** with updated `user_type` to avoid token mismatch issues.

**Simple API:** Only requires `new_user_type` field - the backend handles everything else automatically.

---

## API Endpoint

### Switch Role

**Endpoint:** `POST /api/1/profiles/switch-role/`

**Headers:**
```
Authorization: Bearer <access_token>
Content-Type: application/json
```

---

## Request Format

### Switch from Seeker to Provider

```json
{
  "new_user_type": "provider"
}
```

**That's it!** The system will:
- Keep the user's existing `service_type` from when they were a provider before
- Generate a `provider_id` if switching for the first time
- Create a wallet if it doesn't exist
- Preserve all previous provider data

### Switch from Provider to Seeker

```json
{
  "new_user_type": "seeker"
}
```

**That's it!** The system will:
- Keep all provider data (wallet, ratings, provider_id) for when they switch back
- Set provider to offline status

---

## Success Response

**Status Code:** `200 OK`

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
    "can_access_app": false,
    "mobile_number": "+1234567890",
    "profile_photo": "https://...",
    "created_at": "2025-01-15T10:30:00Z",
    "updated_at": "2025-01-20T14:22:00Z"
  }
}
```

**Important:** The response includes **NEW JWT tokens** (`access_token` and `refresh_token`) that contain the updated `user_type`. You must replace the old tokens with these new ones.

---

## Error Responses

### 400 Bad Request - Active Work Orders (Seeker)

```json
{
  "status": "error",
  "message": "You have active work orders as a seeker. Please complete or cancel them before switching roles.",
  "errors": {
    "error": ["You have active work orders as a seeker. Please complete or cancel them before switching roles."]
  }
}
```

### 400 Bad Request - Active Work Orders (Provider)

```json
{
  "status": "error",
  "message": "You have active work orders as a provider. Please complete them before switching roles.",
  "errors": {
    "error": ["You have active work orders as a provider. Please complete them before switching roles."]
  }
}
```

### 400 Bad Request - Provider is Online

```json
{
  "status": "error",
  "message": "Please go offline before switching roles.",
  "errors": {
    "error": ["Please go offline before switching roles."]
  }
}
```


### 400 Bad Request - Same Role

```json
{
  "status": "error",
  "message": "You are already a provider.",
  "errors": {
    "error": ["You are already a provider."]
  }
}
```

### 404 Not Found - Profile Not Found

```json
{
  "status": "error",
  "message": "User profile not found. Please complete profile setup first."
}
```

### 500 Internal Server Error

```json
{
  "status": "error",
  "message": "An unexpected server error occurred. Please try again."
}
```

---

## JWT Token Updates

### Why New Tokens Are Returned

JWT tokens contain `user_type` in their payload. Since tokens are **immutable**, the old token will still have the old role even after switching in the database.

**Old Token Payload (before switch):**
```json
{
  "user_id": 123,
  "mobile_number": "+1234567890",
  "user_type": "seeker"  ← OLD
}
```

**New Token Payload (after switch):**
```json
{
  "user_id": 123,
  "mobile_number": "+1234567890",
  "user_type": "provider"  ← UPDATED!
}
```

**You MUST replace the old token with the new one returned in the response.**

---

## Frontend Integration

### JavaScript Example

```javascript
async function switchRole(newUserType) {
  try {
    const response = await fetch('/api/1/profiles/switch-role/', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        new_user_type: newUserType
      })
    });

    const result = await response.json();

    if (response.ok) {
      // ✅ IMPORTANT: Replace old tokens with new ones
      localStorage.setItem('access_token', result.access_token);
      localStorage.setItem('refresh_token', result.refresh_token);

      // Update UI with new profile data
      updateUserProfile(result.data);

      console.log('✅ Role switched successfully:', result.message);
      return result;

    } else {
      // Handle error
      console.error('❌ Error:', result.message);
      showErrorMessage(result.message);
      return null;
    }

  } catch (error) {
    console.error('❌ Network error:', error);
    showErrorMessage('Network error. Please try again.');
    return null;
  }
}

// Usage examples:
switchRole('provider');  // Switch to provider
switchRole('seeker');    // Switch to seeker
```

### React Example

```jsx
const handleSwitchRole = async (newUserType) => {
  setLoading(true);

  try {
    const response = await fetch('/api/1/profiles/switch-role/', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        new_user_type: newUserType
      })
    });

    const result = await response.json();

    if (response.ok) {
      // ✅ Update tokens
      localStorage.setItem('access_token', result.access_token);
      localStorage.setItem('refresh_token', result.refresh_token);

      // ✅ Update app state
      setUserProfile(result.data);
      setUserType(result.data.user_type);

      toast.success(result.message);
    } else {
      toast.error(result.message);
    }
  } catch (error) {
    toast.error('Failed to switch role');
  } finally {
    setLoading(false);
  }
};

// Usage:
<button onClick={() => handleSwitchRole('provider')}>
  Switch to Provider
</button>
<button onClick={() => handleSwitchRole('seeker')}>
  Switch to Seeker
</button>
```

---

## Validation Rules

### User Can Switch When:
- ✅ No active work orders (as seeker or provider)
- ✅ Provider is offline (`is_active_for_work = false`)
- ✅ No recent wallet transactions (within last 5 minutes)
- ✅ Valid target role (seeker or provider)

### User Cannot Switch When:
- ❌ Has active work orders (status: pending, accepted, in_progress)
- ❌ Provider is currently online/active for work
- ❌ Recent wallet transactions detected
- ❌ Invalid user_type or service_type
- ❌ Trying to switch to the same role

---

## Data Preservation

When switching roles, the following data is **preserved**:

- ✅ Provider ID (kept when switching back to provider)
- ✅ Wallet balance
- ✅ Ratings and reviews
- ✅ Work history
- ✅ Service-specific data
- ✅ Portfolio images

---

## Testing

### Test Case 1: Switch Seeker → Provider

```bash
curl -X POST http://localhost:8000/api/1/profiles/switch-role/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "new_user_type": "provider"
  }'
```

**Expected:** Returns new tokens with `user_type: "provider"`

### Test Case 2: Switch Provider → Seeker

```bash
curl -X POST http://localhost:8000/api/1/profiles/switch-role/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "new_user_type": "seeker"
  }'
```

**Expected:** Returns new tokens with `user_type: "seeker"`

### Test Case 3: Blocked by Active Work

```bash
# User has active work order, should fail
curl -X POST http://localhost:8000/api/1/profiles/switch-role/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "new_user_type": "provider"
  }'
```

**Expected:** 400 error with message about active work orders

---

## Related Files

- **Endpoint:** `apps/profiles/views.py:795` - `switch_role_api()`
- **Serializer:** `apps/profiles/serializers.py:1372` - `RoleSwitchSerializer`
- **Validation:** `apps/profiles/utils.py` - `can_switch_role()`, `validate_role_switch_data()`
- **Models:** `apps/profiles/models.py` - `UserProfile`, `RoleSwitchHistory`
- **JWT Utils:** `apps/authentication/utils/jwt_utils.py` - `get_tokens_for_user()`

---

## Summary

1. ✅ Call `POST /api/1/profiles/switch-role/` with new role
2. ✅ Receive **new JWT tokens** in the response
3. ✅ **Replace old tokens** with new ones in localStorage/cookies
4. ✅ Continue using the app with updated role
5. ✅ All user data is preserved (wallet, ratings, provider_id, etc.)

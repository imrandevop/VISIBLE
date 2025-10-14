# Provider Referral System

## Overview
The referral system allows existing providers to refer new providers using their unique provider ID. Both the referrer and the new provider receive wallet rewards when a referral is successfully completed.

## Features
- **Referral Code**: Each provider's `provider_id` acts as their unique referral code
- **Automatic Rewards**:
  - Existing provider (referrer): ¹100
  - New provider (referee): ¹50
- **Validation**: Prevents self-referrals and duplicate referral code usage
- **Wallet Integration**: Rewards are automatically credited to provider wallets
- **JWT Authentication**: Secure API endpoints using JWT tokens

## API Endpoints

### 1. Apply Referral Code (POST)
**Endpoint**: `POST /api/1/referral/`

**Description**: New providers can apply a referral code to get rewards

**Headers**:
```
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

**Request Body**:
```json
{
    "referral_code": "AB12345678"
}
```

**Success Response** (200):
```json
{
    "success": true,
    "message": "Referral code applied successfully! You earned ¹50 and your referrer earned ¹100",
    "data": {
        "referrer_reward": 100.00,
        "referee_reward": 50.00,
        "your_new_balance": 50.00
    }
}
```

**Error Responses**:

*Invalid referral code (400)*:
```json
{
    "success": false,
    "message": "Validation failed",
    "errors": {
        "referral_code": ["Invalid referral code. Please check and try again."]
    }
}
```

*Self-referral attempt (400)*:
```json
{
    "success": false,
    "message": "Validation failed",
    "errors": {
        "non_field_errors": ["You cannot use your own referral code."]
    }
}
```

*Already used referral code (400)*:
```json
{
    "success": false,
    "message": "Validation failed",
    "errors": {
        "non_field_errors": ["You have already used a referral code. Each provider can only use one referral code."]
    }
}
```

### 2. Get Referral Statistics (GET)
**Endpoint**: `GET /api/1/referral/`

**Description**: Get referral statistics for the current provider

**Headers**:
```
Authorization: Bearer <jwt_token>
```

**Success Response** (200):
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
            }
        ]
    }
}
```

## Models

### ProviderReferral
Tracks who referred whom.

**Fields**:
- `referred_provider` - The new provider who used the referral code (OneToOne)
- `referrer_provider` - The existing provider who shared the code (ForeignKey)
- `referral_code_used` - The provider_id used as referral code
- `status` - Referral status (pending/completed/cancelled)
- `completed_at` - Timestamp when referral was completed

### ReferralReward
Tracks rewards given for referrals.

**Fields**:
- `referral` - Link to the ProviderReferral
- `provider` - Provider who received the reward
- `reward_type` - Type of reward (referrer/referee)
- `amount` - Reward amount
- `currency` - Currency (default: INR)
- `is_credited` - Whether reward was credited
- `credited_at` - When reward was credited

## Validation Rules

1. **Self-Referral Prevention**: Providers cannot use their own referral code
2. **One-Time Use**: Each provider can only use one referral code (enforced via OneToOne relationship)
3. **Valid Provider ID**: Referral code must be a valid provider_id from an existing provider
4. **Provider Only**: Only users with user_type='provider' can use referral codes

## Wallet Integration

The system automatically:
1. Creates or retrieves wallets for both providers
2. Credits ¹100 to the referrer's wallet
3. Credits ¹50 to the new provider's wallet
4. Creates WalletTransaction records for both transactions
5. Creates ReferralReward records for tracking

All operations are performed within a database transaction to ensure data consistency.

## Admin Interface

Both models are registered in Django admin with:
- Search functionality
- List filters
- Display of key fields
- Readonly fields for timestamps

## Testing

To test the referral system:

1. Create two provider accounts
2. Get the provider_id of the first provider (this is their referral code)
3. Use the second provider's JWT token to call POST /api/1/referral/ with the first provider's ID
4. Check wallet balances for both providers
5. Use GET /api/1/referral/ to view referral statistics

## Database Migrations

Run these commands to set up the database:
```bash
python manage.py makemigrations referrals
python manage.py migrate referrals
```

## Security Considerations

- All endpoints require JWT authentication
- Validation prevents abuse (self-referral, duplicate usage)
- Database transactions ensure data consistency
- Provider IDs are validated before processing

## Future Enhancements

Possible improvements:
- Referral expiration dates
- Tiered rewards based on referee activity
- Referral limits per provider
- Analytics dashboard for tracking referral performance

# Instagram Direct Messaging Integration Guide

This guide provides complete, step-by-step instructions for connecting Instagram Direct Messaging to the Gabster AI platform using the Meta Graph API.

---

## 📋 Architectural Overview

```text
+-----------------------+         +-------------------------------+
|   Instagram User      |         |  TechVibe Instagram Account   |
|   (Mobile App / Web)  | ------> |  (Professional Business/Creator|
+-----------------------+         +-------------------------------+
                                                 |
                                                 v (Meta Graph API)
                                  +-------------------------------+
                                  |    Meta Webhook Gateway       |
                                  +-------------------------------+
                                                 |
                                                 v POST /webhooks/instagram
                                  +-------------------------------+
                                  |    Gabster AI Backend         |
                                  |    (FastAPI + Celery)         |
                                  +-------------------------------+
                                     |           |           |
               +---------------------+           |           +---------------------+
               v                                 v                                 v
   +-----------------------+         +-----------------------+         +-----------------------+
   | PostgreSQL Storage    |         | pgvector / RAG KB     |         | Google Gemini AI      |
   | (Contacts & Messages) |         | (Knowledge Retrieval) |         | (Response Generation) |
   +-----------------------+         +-----------------------+         +-----------------------+
                                                 |
                                                 v POST /me/messages
                                  +-------------------------------+
                                  | Meta Instagram Send API       |
                                  +-------------------------------+
                                                 |
                                                 v
                                  +-------------------------------+
                                  | User Receives Instant Reply   |
                                  +-------------------------------+
```

---

##  Prerequisites

Before starting, ensure you have:
1. An **Instagram Account** that you can convert to a Professional account.
2. An active **Facebook Page** (e.g., TechVibe Members Club).
3. A **Meta for Developers Account** with admin access to your Meta App.
4. An active Ngrok tunnel or public domain pointing to port `8000`.

---

## Step-by-Step Setup Instructions

### Step 1: Convert Instagram Account to Professional

Meta Graph API messaging is restricted to **Professional** (Business or Creator) accounts. Personal accounts do not have API access.

1. Open the **Instagram App** on your mobile device.
2. Navigate to your Profile &rarr; tap the top-right menu icon (**☰**) &rarr; select **Settings and Privacy**.
3. Scroll down and tap **Account type and tools**.
4. Tap **Switch to Professional Account**.
5. Select either **Business** or **Creator** and complete the on-screen prompts.

---

### Step 2: Link Your Instagram Account to Your Facebook Page

Your Instagram account must be connected to the Facebook Page associated with your Meta Developer App.

#### Option A: From the Instagram Mobile App
1. Go to your Instagram Profile &rarr; tap **Edit Profile**.
2. Under **Public Business Information**, tap **Page**.
3. Select your Facebook Page (**TechVibe**) and confirm the link.

#### Option B: From Facebook Desktop
1. Open [Facebook](https://www.facebook.com/) and switch to your Page (**TechVibe**).
2. Go to **Settings & Privacy** &rarr; **Settings** &rarr; **Linked Accounts**.
3. Select **Instagram** &rarr; click **Connect Account** and log in to authorize.

---

### Step 3: Enable "Allow Access to Messages" (Critical)

> [!IMPORTANT]
> By default, Meta disables third-party bot access to Instagram messages for privacy reasons. If this toggle is not enabled, incoming DMs will **never** trigger webhooks.

1. Open the **Instagram App** on your mobile device.
2. Go to **Settings and Privacy**.
3. Tap **Messages and story replies** &rarr; tap **Message controls**.
4. Scroll to **Connected tools** and toggle **ON** &rarr; **Allow access to messages**.

---

### Step 4: Configure the Webhook in Meta for Developers

1. Visit [Meta for Developers](https://developers.facebook.com/apps/) and select your App (**TechVibe Members Club**).
2. If not already added, click **Add Product** in the sidebar and add **Messenger** (or **Instagram Graph API**).
3. In the left navigation menu, go to **Webhooks** (or under Messenger &rarr; Instagram Settings):
   - From the dropdown, select **Instagram**.
   - Click **Subscribe to this object** (or **Edit Callback URL**).
4. Fill in your endpoint details:
   - **Callback URL:**
     ```text
     https://salad-clapper-dowry.ngrok-free.dev/webhooks/instagram
     ```
   - **Verify Token:**
     ```text
     gabster_meta_verify_token_secure_string
     ```
5. Click **Verify and Save**. Meta will execute an immediate handshake check against Gabster AI, which will respond with `200 OK`.
6. Under Instagram Webhook fields, click **Subscribe** for:
   - `messages`
   - `messaging_postbacks`
   - `message_reactions`

---

### Step 5: Assign Assets to Your System User in Meta Business Suite

To allow your permanent System User token to read and send messages on behalf of your Instagram account:

1. Open [Meta Business Suite &rarr; Business Settings](https://business.facebook.com/settings).
2. In the left sidebar, navigate to **Users** &rarr; **System Users**.
3. Select your System User (e.g., `gabster-system-user`).
4. Click **Add Assets**:
   - **Pages:** Select your Facebook Page (**TechVibe**) &rarr; enable **Full Control (Manage Page)**.
   - **Instagram Accounts:** Select your connected Instagram account &rarr; enable **Full Control**.
5. Click **Save Changes**.

---

## ⚙️ Backend Architecture in Gabster AI

The following components are implemented in the project:

### 1. Webhook Router (`app/api/webhooks/router.py`)
- **`GET /webhooks/instagram`**: Validates the Meta handshake using `hub.challenge` and `META_WEBHOOK_VERIFY_TOKEN`.
- **`POST /webhooks/instagram`**: Ingests real-time direct message events and spawns an asynchronous processing task.

### 2. Instagram Channel Service (`app/domains/channels/instagram_service.py`)
- **Inbound Event Processing**: Parses incoming JSON payloads (`object: "instagram"`).
- **Contact Sync**: Upserts contact records in the `contacts` table with `custom_attributes: {"igsid": sender_id, "source": "instagram_direct"}`.
- **Unified Conversation**: Creates or resumes active conversation sessions in `conversations`.
- **RAG Grounding & Gemini Generation**: Retrieves semantic knowledge chunks from `document_chunks` and generates contextual responses via Google Gemini.
- **Outbound Dispatch**: Sends responses back to the user via Meta Graph API (`POST https://graph.facebook.com/v19.0/me/messages`).
- **Ledger Accounting**: Automatically deducts usage credits in `credit_ledger` and `credit_balances`.

### 3. Outbound Conversation Service (`app/domains/conversations/service.py`)
- Supports manual agent replies sent from the Gabster Unified Inbox UI directly to Instagram DMs using `channel_type == "instagram"` and `custom_attrs["igsid"]`.

### 4. Database Channel Configuration (`channel_accounts` table)
- **Channel ID:** `fc9f2de0-878b-448b-8bad-440c86585577` (Instagram Direct)
- **Account ID:** `00000000-0000-0000-0000-000000000212`
- **Organization ID:** `00000000-0000-0000-0000-000000000200` (TechVibe Members Club)

---

## 🧪 Verification & Testing

### 1. Test Webhook Handshake Verification
Execute the handshake test from your terminal:
```bash
curl -i "http://localhost:8000/webhooks/instagram?hub.mode=subscribe&hub.challenge=test_challenge&hub.verify_token=gabster_meta_verify_token_secure_string"
```
**Expected Response:** HTTP `200 OK` with body `test_challenge`.

### 2. Test Real Inbound Message
Send a direct message from any Instagram user to your connected Instagram account (e.g. `"Hello, how can I join TechVibe?"`).

### 3. Monitor Live Logs
View the live interaction logs in Docker:
```bash
docker compose -f docker/docker-compose.yml logs -f api
```
**Expected Log Output:**
```text
Received Instagram message from IGSID 123456789 to Account ...: 'Hello, how can I join TechVibe?'
Successfully dispatched Instagram DM to IGSID 123456789
Processed Instagram interaction for TechVibe. AI reply sent to 123456789: '...'
```

---

## 🛠️ Troubleshooting

| Issue | Root Cause | Solution |
| :--- | :--- | :--- |
| **No webhook triggered when DM is sent** | "Allow access to messages" is disabled in the Instagram App | Follow Step 3 in Instagram App &rarr; Settings &rarr; Messages &rarr; Message controls &rarr; Connected tools &rarr; Toggle ON "Allow access to messages". |
| **Meta Graph API error (400): "API access blocked"** | The System User token lacks asset assignment for the Page/Instagram account | Follow Step 5 in Meta Business Suite &rarr; System Users &rarr; Add Assets &rarr; Assign Page and Instagram account with Full Control. |
| **Meta Webhook returns 403 Forbidden during setup** | Verification token mismatch | Verify that `hub.verify_token` matches `META_WEBHOOK_VERIFY_TOKEN` in `.env` (`gabster_meta_verify_token_secure_string`). |
| **Instagram Account not showing under Linked Accounts** | Account is still set to Personal | Convert to Business or Creator in Instagram App &rarr; Settings &rarr; Account type and tools. |

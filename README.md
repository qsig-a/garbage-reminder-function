# Garbage Reminder Function

A secure, genericized Google Cloud Function (2nd Gen) that automates waste collection reminders. It monitors a Google Calendar for scheduled garbage/recycling pickup events and dispatches custom SMS reminders to residents via the SignalWire REST API.

This project has been fully restructured for public open-source distribution: it contains **zero hardcoded secrets**, uses **Google Application Default Credentials (ADC)**, supports secure local development/testing, and automates deployments via **GitHub Actions** using highly secure pinned SHAs.

---

## 🏗️ System Architecture

The following diagram illustrates how the system operates:

```mermaid
flowchart TD
    subgraph Google Cloud Platform
        Scheduler["Cloud Scheduler (Daily Cron)"] -->|HTTP GET Request (OIDC Auth)| GCF["Cloud Function (main.py)"]
        GCF -->|Auth via ADC| GoogleAuth["Google Auth Server"]
        GCF -->|Fetch Tomorrow's Events| Calendar["Google Calendar API"]
    end

    subgraph External APIs
        GCF -->|SMS Notification Payload| SignalWire["SignalWire SMS API"]
    end

    subgraph End Users
        SignalWire -->|SMS Reminders| Recipients["Residents (Phone Numbers)"]
    end

    classDef primary fill:#2563eb,stroke:#1d4ed8,color:#ffffff,stroke-width:2px;
    classDef secondary fill:#059669,stroke:#047857,color:#ffffff,stroke-width:2px;
    classDef external fill:#7c3aed,stroke:#6d28d9,color:#ffffff,stroke-width:2px;
    
    class GCF primary;
    class Scheduler,GoogleAuth,Calendar secondary;
    class SignalWire,Recipients external;
```

---

## ✨ Features

- 🔐 **Zero-Secret Codebase**: Ready for public hosting. All credentials, API tokens, calendar IDs, and recipient phone numbers are fetched from runtime environment variables or secure local files.
- 🏢 **Multi-Unit Support**: Dynamically resolves resident lists for different housing units based on Google Calendar event summaries.
- 🔑 **Standardized Authentication**: Leverages standard Google Application Default Credentials (ADC), integrating transparently with GCP's metadata service in production and secure local credential files during development.
- 🚀 **CI/CD Automation**: Deploys securely from GitHub to GCP via GitHub Actions using strict, pinned commit SHAs to prevent supply chain vulnerabilities.
- ⚙️ **Local Testing Experience**: Supports seamless local development using Python's `functions-framework` and `.env`/`units.json` fallback mechanics.

---

## 🛠️ Configuration Details

The function requires the following configuration environment variables in production (which should be set as GitHub Secrets or directly on the Cloud Function):

| Environment Variable | Description | Example / Format |
| :--- | :--- | :--- |
| `CALENDAR_ID` | The Google Calendar ID containing pickup schedules | `pv1f...amgk@group.calendar.google.com` |
| `SIGNALWIRE_PROJECT_ID` | SignalWire Project UUID | `00000000-0000-0000-0000-000000000000` |
| `SIGNALWIRE_TOKEN` | SignalWire API Token / Key | `PTyourtokenhere...` |
| `SIGNALWIRE_SPACE_URL` | SignalWire Space domain | `your-space.signalwire.com` |
| `SIGNALWIRE_FROM_NUMBER` | The SignalWire phone number used as the SMS sender | `+15555550100` |
| `UNIT_LIST_JSON` | A JSON-formatted mapping of units to recipient phone numbers | *See "Resident Directory Format" below* |

### Resident Directory Format
The mapping matches the summary in Google Calendar (e.g. if the event name contains `"123 Unit A"`, it matches the unit `"123 Unit A"`).

#### Env Var Format (`UNIT_LIST_JSON`):
```json
{"123 Unit A": ["+15555550101", "+15555550102"], "123 Unit B": ["+15555550101", "+15555550103"]}
```

#### Local File Format (`units.json`):
Place this in the root directory for local testing. It is automatically ignored by Git.
```json
{
  "123 Unit A": [
    "+15555550101",
    "+15555550102"
  ],
  "123 Unit B": [
    "+15555550101",
    "+15555550103"
  ]
}
```

---

## 💻 Local Development & Testing

You can run the function locally to verify its behavior before deployment.

### 1. Prerequisite Setup
Clone the repository, navigate into the directory, and set up a virtual environment:
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment (Windows)
.venv\Scripts\activate

# Activate virtual environment (macOS/Linux)
source .venv/bin/activate

# Install required dependencies
pip install -r requirements.txt
```

### 2. Configure Local Environment
Create a `.env` file in the root of the project (this is Git-ignored):
```env
CALENDAR_ID=your_calendar_id@group.calendar.google.com
SIGNALWIRE_PROJECT_ID=your-project-uuid
SIGNALWIRE_TOKEN=your-token
SIGNALWIRE_SPACE_URL=your-space.signalwire.com
SIGNALWIRE_FROM_NUMBER=+1XXXXXXXXXX
```

Create a `units.json` file in the root of the project:
```json
{
  "123 Unit A": ["+1XXXXXXXXXX"]
}
```

Finally, place your Google Service Account credential file (`creds.json`) in the root directory.

### 3. Run the Function Locally
Launch the function locally using the `functions-framework`:
```bash
# Windows
$env:PORT="8080"
functions-framework --target=main --signature-type=http

# macOS/Linux/Bash
PORT=8080 functions-framework --target=main --signature-type=http
```

You can now trigger the function by making an HTTP GET request to:
`http://localhost:8080`

---

## 🛡️ GCP Production Setup

Deploying securely without long-lived private key files requires two GCP components: **Google Calendar access** and **Workload Identity Federation**.

### 1. Google Calendar API Configuration
1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and enable the **Google Calendar API**.
2. Create or identify the Service Account assigned to run the Cloud Function.
3. Open the **Google Calendar** settings that hosts your garbage collection schedules.
4. Under "Share with specific people or groups", click **Add people and groups** and share the calendar with your Cloud Function Service Account's email address with **See all event details** (Read-only) permissions.

### 2. Workload Identity Federation (OIDC) Setup
To enable passwordless, secure deployments from GitHub Actions to your GCP project, run the setup commands in your terminal. Choose the instructions below that match your operating system:

#### Option A: macOS / Linux (Bash)
```bash
# Define configuration variables
export PROJECT_ID="YOUR_GCP_PROJECT_ID"
export WORKLOAD_POOL="github-actions-pool"
export WORKLOAD_PROVIDER="github-provider"
export REPO_OWNER="your-github-username-or-org"
export REPO_NAME="garbage-reminder-function"
export SERVICE_ACCOUNT_EMAIL="your-service-account@$PROJECT_ID.iam.gserviceaccount.com"

# 1. Create the Workload Identity Pool
gcloud iam workload-identity-pools create "$WORKLOAD_POOL" \
    --project="$PROJECT_ID" \
    --location="global" \
    --display-name="GitHub Actions Pool"

# 2. Create the OIDC Provider inside the pool
gcloud iam workload-identity-pools providers create-oidc "$WORKLOAD_PROVIDER" \
    --project="$PROJECT_ID" \
    --location="global" \
    --workload-identity-pool="$WORKLOAD_POOL" \
    --display-name="GitHub OIDC Provider" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository=='$REPO_OWNER/$REPO_NAME'"

# 3. Allow GitHub Actions to assume your Service Account role
gcloud iam service-accounts add-iam-policy-binding "$SERVICE_ACCOUNT_EMAIL" \
    --role="roles/iam.workloadIdentityUser" \
    --member="principalSet://iam.googleapis.com/projects/$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')/locations/global/workloadIdentityPools/$WORKLOAD_POOL/attribute.repository/$REPO_OWNER/$REPO_NAME"

# 4. Grant your Service Account permissions to deploy Cloud Functions
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
    --role="roles/cloudfunctions.developer"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
    --role="roles/iam.serviceAccountUser"
```

#### Option B: Windows (PowerShell)
```powershell
# Define configuration variables
$PROJECT_ID="YOUR_GCP_PROJECT_ID"
$WORKLOAD_POOL="github-actions-pool"
$WORKLOAD_PROVIDER="github-provider"
$REPO_OWNER="your-github-username-or-org"
$REPO_NAME="garbage-reminder-function"
$SERVICE_ACCOUNT_EMAIL="your-service-account@${PROJECT_ID}.iam.gserviceaccount.com"

# 1. Create the Workload Identity Pool
gcloud iam workload-identity-pools create $WORKLOAD_POOL `
    --project=$PROJECT_ID `
    --location="global" `
    --display-name="GitHub Actions Pool"

# 2. Create the OIDC Provider inside the pool
gcloud iam workload-identity-pools providers create-oidc $WORKLOAD_PROVIDER `
    --project=$PROJECT_ID `
    --location="global" `
    --workload-identity-pool=$WORKLOAD_POOL `
    --display-name="GitHub OIDC Provider" `
    --issuer-uri="https://token.actions.githubusercontent.com" `
    --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" `
    --attribute-condition="assertion.repository=='$REPO_OWNER/$REPO_NAME'"

# 3. Allow GitHub Actions to assume your Service Account role
$PROJECT_NUMBER = (gcloud projects describe $PROJECT_ID --format="value(projectNumber)").Trim()
gcloud iam service-accounts add-iam-policy-binding $SERVICE_ACCOUNT_EMAIL `
    --role="roles/iam.workloadIdentityUser" `
    --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$WORKLOAD_POOL/attribute.repository/$REPO_OWNER/$REPO_NAME"

# 4. Grant your Service Account permissions to deploy Cloud Functions
gcloud projects add-iam-policy-binding $PROJECT_ID `
    --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" `
    --role="roles/cloudfunctions.developer"

gcloud projects add-iam-policy-binding $PROJECT_ID `
    --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" `
    --role="roles/iam.serviceAccountUser"
```

Once completed, retrieve your **Workload Identity Provider identifier** using:

##### macOS / Linux (Bash)
```bash
gcloud iam workload-identity-pools providers describe "$WORKLOAD_PROVIDER" \
    --project="$PROJECT_ID" \
    --location="global" \
    --workload-identity-pool="$WORKLOAD_POOL" \
    --format="value(name)"
```

##### Windows (PowerShell)
```powershell
gcloud iam workload-identity-pools providers describe $WORKLOAD_PROVIDER `
    --project=$PROJECT_ID `
    --location="global" `
    --workload-identity-pool=$WORKLOAD_POOL `
    --format="value(name)"
```

It will have the format: `projects/1234567890/locations/global/workloadIdentityPools/github-actions-pool/providers/github-provider`

---

## 🚀 GitHub Actions Deployment

The CI/CD pipeline defined in [.github/workflows/deploy.yml](.github/workflows/deploy.yml) deploys your changes to Google Cloud Run functions on push to the `main` branch.

### Required GitHub Secret Configurations
Go to your GitHub Repository -> **Settings** -> **Secrets and variables** -> **Actions** and add the following **Repository Secrets**:

| Secret Name | Value Example | Description |
| :--- | :--- | :--- |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/123456789/locations/global/workloadIdentityPools/...` | OIDC Provider identifier |
| `GCP_SERVICE_ACCOUNT_EMAIL` | `deployer@my-project.iam.gserviceaccount.com` | Deployment Service Account |
| `CALENDAR_ID` | `calendar-id@group.calendar.google.com` | Google Calendar ID |
| `SIGNALWIRE_PROJECT_ID` | `00000000-0000-0000-0000-000000000000` | SignalWire project ID |
| `SIGNALWIRE_TOKEN` | `PTyourtokenhere...` | SignalWire API Token |
| `SIGNALWIRE_SPACE_URL` | `your-space.signalwire.com` | SignalWire Space Domain |
| `SIGNALWIRE_FROM_NUMBER` | `+15555550100` | SignalWire Sender Number |
| `UNIT_LIST_JSON` | `{"Unit A": ["+1..."]}` | Resident Directory mapping |

### Optional GitHub Variables
To customize GCP location settings, add this under **Variables**:

| Variable Name | Value Example | Description | Default |
| :--- | :--- | :--- | :--- |
| `GCP_REGION` | `us-central1` | Deployment target region | `us-east1` |

---

## 🕒 Automating Executions via Cloud Scheduler

To trigger the Cloud Function automatically every day (e.g. at 5:00 PM Eastern), configure a **Google Cloud Scheduler** job:

1. In the GCP Console, go to **Cloud Scheduler** and click **Create Job**.
2. **Frequency**: Set to `0 17 * * *` (5:00 PM Eastern daily). Select your timezone (e.g., `United States/Eastern`).
3. **Target Type**: HTTP
4. **URL**: The URL of your deployed Cloud Function endpoint (obtained from your GitHub Actions deployment logs or Cloud Console).
5. **HTTP Method**: GET
6. **Auth Header**: **Add OIDC token**
7. **Service Account**: Select a service account with `Cloud Functions Invoker` (or `Cloud Run Invoker` for 2nd Gen) permissions to invoke the function securely.

This secures the endpoint, preventing unauthenticated external users from triggering text alerts manually!

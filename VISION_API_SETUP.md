# Google Vision API Setup Instructions

## The Issue:
Your Google Vision API is not working because it needs proper authentication credentials.

## Quick Fix (Current):
I've added a fallback system that validates images without AI detection. The system now works but won't identify specific animals.

## To Enable Full AI Detection:

### Option 1: Set Environment Variable
1. Get your Google Cloud service account key file
2. Set environment variable:
   ```
   set GOOGLE_APPLICATION_CREDENTIALS=path\to\your\service-account-key.json
   ```

### Option 2: Use the gcloud-key.json file
1. Replace the empty `gcloud-key.json` with your actual Google Cloud credentials
2. The app will automatically use this file

## How to Get Google Cloud Credentials:

1. **Go to Google Cloud Console**: https://console.cloud.google.com/
2. **Create/Select Project**: Create a new project or select existing
3. **Enable Vision API**: 
   - Go to "APIs & Services" > "Library"
   - Search for "Cloud Vision API"
   - Click "Enable"
4. **Create Service Account**:
   - Go to "IAM & Admin" > "Service Accounts"
   - Click "Create Service Account"
   - Give it a name and description
   - Grant "Cloud Vision API User" role
5. **Download Key**:
   - Click on the service account
   - Go to "Keys" tab
   - Click "Add Key" > "Create New Key"
   - Choose JSON format
   - Download and save as `gcloud-key.json`

## Current Status:
✅ System works without API (basic image validation)
⚠️ No AI animal detection (shows "Animal" for all valid images)
🔧 Need credentials for full AI functionality

## Alternative:
You can also disable the Vision API completely and just use basic image validation by keeping the current setup.
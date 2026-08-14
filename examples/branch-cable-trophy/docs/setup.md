# Setup

## Requirements

- Python 3.10 or newer.
- No third-party Python packages.
- An Onshape account and a one-time API key with document read/write access.
- The target Onshape document and workspace IDs in `config/onshape-state.json`.

The FeatureScript itself has no dependency on Python, local files, credentials, or REST APIs. Python is used only to deploy and validate the model automatically.

## Credentials

Create `onshape-credentials.json` at the project root:

```json
{
  "baseUrl": "https://cad.onshape.com",
  "accessKey": "YOUR_ACCESS_KEY",
  "secretKey": "YOUR_SECRET_KEY"
}
```

Or use a short-lived OAuth access token:

```json
{
  "baseUrl": "https://cad.onshape.com",
  "accessToken": "YOUR_ACCESS_TOKEN"
}
```

Protect the file:

```bash
chmod 600 onshape-credentials.json
```

The client never prints credentials or copies them into generated state and reports. Destroy or revoke the one-time key after validation.

## Manual Feature Studio installation

1. In Onshape, create a Feature Studio.
2. Keep the two version/import lines Onshape generates for the current environment.
3. Paste the body of `branchCableTrophyDisplay.fs`, or paste the whole file if its version matches the generated header.
4. Compile the Feature Studio.
5. In a Part Studio, add `Branch cable trophy display` as a custom feature.
6. Use the defaults for the detailed reference-like result.

The source currently targets FeatureScript/standard-library version 3029, which was read from the generated Feature Studio on 2026-08-05.

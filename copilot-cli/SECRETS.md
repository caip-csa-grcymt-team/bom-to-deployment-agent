# Secrets Configuration

Required secrets for the GSIS Copilot CLI infrastructure provisioning pipeline.

## GitHub Actions Secrets

Configure these secrets in your GitHub repository settings under **Settings > Secrets and variables > Actions**.

| Secret | Required | Description | Example |
|--------|----------|-------------|---------|
| `COPILOT_PAT` | Yes | GitHub Personal Access Token with Copilot permissions | `ghp_xxxxxxxxxxxx` |
| `IPAM_FQDN` | Yes | Azure IPAM engine fully-qualified domain name | `ipam.contoso.com` |
| `IPAM_SPACE` | Yes | IPAM space name for VNet allocation | `default` |
| `IPAM_BLOCK` | Yes | IPAM block name within the space | `azure-production` |
| `IPAM_ENGINE_CLIENT_ID` | Yes | Azure AD application (client) ID for IPAM engine | `00000000-0000-0000-0000-000000000000` |

## GitHub PAT Requirements

The `COPILOT_PAT` requires these permissions:

| Permission | Scope | Reason |
|------------|-------|--------|
| `user_copilot_requests:read` | User | Execute Copilot CLI requests |
| `repo` | Repository | Read/write repository files |
| `workflow` | Actions | Trigger workflows (optional) |

### Creating the PAT

1. Go to **GitHub Settings > Developer settings > Personal access tokens > Fine-grained tokens**
2. Create new token with:
   - Repository access: Select the GSIS repository
   - Permissions:
     - Contents: Read and write
     - Pull requests: Read and write (if creating PRs)
3. Copy the token and add as `COPILOT_PAT` secret

## Azure DevOps Variable Group

For Azure DevOps pipelines, create a variable group named `copilot-secrets`:

1. Go to **Pipelines > Library > Variable groups**
2. Create group named `copilot-secrets`
3. Add these variables:

| Variable | Secret | Description |
|----------|--------|-------------|
| `COPILOT_PAT` | Yes | GitHub PAT (same as above) |
| `IPAM_FQDN` | Yes | IPAM engine FQDN |
| `IPAM_SPACE` | No | IPAM space name |
| `IPAM_BLOCK` | No | IPAM block name |
| `IPAM_ENGINE_CLIENT_ID` | Yes | IPAM engine client ID |

## IPAM Service Principal

The IPAM client authenticates using `DefaultAzureCredential`. In CI/CD, configure:

### GitHub Actions (OIDC)

```yaml
permissions:
  id-token: write
  contents: read

steps:
  - uses: azure/login@v2
    with:
      client-id: ${{ secrets.AZURE_CLIENT_ID }}
      tenant-id: ${{ secrets.AZURE_TENANT_ID }}
      subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
```

### Azure DevOps (Service Connection)

Use an Azure Resource Manager service connection with federated credentials.

## Local Development

For local testing, set environment variables:

```powershell
# Required for Copilot CLI
$env:GH_TOKEN = "ghp_your_token_here"

# Required for IPAM (if testing IPAM integration)
$env:IPAM_FQDN = "ipam.yourdomain.com"
$env:IPAM_SPACE = "default"
$env:IPAM_BLOCK = "azure-production"
$env:IPAM_ENGINE_CLIENT_ID = "00000000-0000-0000-0000-000000000000"

# Azure credentials (for IPAM token acquisition)
az login
```

## Security Notes

- Never commit secrets to the repository
- Rotate the GitHub PAT periodically
- Use environment-specific IPAM blocks (dev, prod)
- The IPAM engine client ID is the application ID, not a secret itself
- Actual authentication uses Azure AD tokens acquired at runtime

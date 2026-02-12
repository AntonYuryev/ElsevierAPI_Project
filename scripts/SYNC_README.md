# ElsevierAPI - GitHub Synchronization Setup

## Repository Information
- **GitHub Repository**: https://github.com/AntonYuryev/ElsevierAPI
- **Remote Structure**: The ElsevierAPI code is in the `ElsevierAPI/` subdirectory of the repository
- **Local Structure**: This directory contains the ElsevierAPI code at the root level

## Initial Setup (Already Completed)
The local directory has been initialized as a git repository and synchronized with the GitHub repository on **February 12, 2026**.

Git configuration:
- Remote: `origin` → https://github.com/AntonYuryev/ElsevierAPI.git
- Branch: `main`
- Sparse checkout disabled (full repository access)

## Files Preserved Locally (Not Synced)
The following files/directories are preserved according to `.gitignore`:
- `config/` - Local configuration directory
- `APIconfig.json` - **Contains your credentials - never synced!**
- `.cache/` and `cache/` - Local cache directories
- `DemoOutput/` - Demo output directory
- `__pycache__/` - Python cache
- Other Python/IDE temporary files

## How to Sync Updates from GitHub

### Option 1: Use the Sync Script (Recommended)
Run the provided PowerShell script:
```powershell
.\sync_from_github.ps1
```

The script will:
1. Fetch latest changes from GitHub
2. Extract the ElsevierAPI subdirectory from the remote
3. Sync files to your local root directory
4. Preserve your local config and credentials
5. Ask if you want to commit the changes

### Option 2: Manual Sync
If you prefer manual control:

```powershell
# 1. Fetch latest changes
git fetch origin main

# 2. Checkout the ElsevierAPI subdirectory from remote
git checkout origin/main -- ElsevierAPI/

# 3. Copy files to root (excluding credentials)
Copy-Item -Path .\ElsevierAPI\* -Destination . -Recurse -Force -Exclude "APIconfig.json"

# 4. Remove the temporary subdirectory
Remove-Item -Path .\ElsevierAPI -Recurse -Force

# 5. Review and commit changes
git status
git add -A
git commit -m "Sync from GitHub ElsevierAPI"
```

## Important Notes

1. **Credentials Protection**: Your `APIconfig.json` and `config/` directory are automatically excluded from syncing and version control.

2. **Structure Difference**: The GitHub repository has ElsevierAPI as a subdirectory, but your local copy has it at the root level. The sync scripts handle this difference automatically.

3. **Version Tracking**: Your local commits track when you synced with GitHub, making it easy to see when updates were applied.

4. **Conflict Resolution**: If you've made local changes to files that are also updated on GitHub, you may need to resolve conflicts manually.

## Checking What's New on GitHub
To see what files have changed on GitHub without syncing:
```powershell
git fetch origin main
git diff HEAD origin/main -- ElsevierAPI/
```

## Repository Status
Check your current status:
```powershell
git status
```

View commit history:
```powershell
git log --oneline -10
```

## Getting Help
- GitHub Repository: https://github.com/AntonYuryev/ElsevierAPI
- Report issues or check for updates on the GitHub repository

# Intune Packager - Enterprise Software Packaging Automation

A Python application that automates the lifecycle of enterprise software packaging for Microsoft Intune deployment.

## Features

- **Installer Processing**: Detect and validate EXE/MSI installers, extract metadata
- **Packaging**: Convert installers to `.intunewin` format using IntuneWinAppUtil
- **Intune Upload**: Upload packages to Microsoft Intune via Graph API
- **Deployment Reports**: Generate HTML/CSV reports of deployment status

## Prerequisites

- Python 3.9+
- Azure AD App Registration with `DeviceManagementApps.ReadWrite.All` permission
- Windows OS (required for IntuneWinAppUtil)

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Copy `config.example.yaml` to `config.yaml` and fill in your Azure AD credentials:

```yaml
azure:
  tenant_id: "your-tenant-id"
  client_id: "your-client-id"
  client_secret: "your-client-secret"
```

## Usage

### Package an Installer
```bash
python -m intune_packager package "C:\path\to\installer.msi" -o ./output
```

### Upload to Intune
```bash
python -m intune_packager upload "./output/installer.intunewin" --name "My App" --version "1.0.0"
```

### Full Pipeline (Package + Upload)
```bash
python -m intune_packager deploy "C:\path\to\installer.msi" --name "My App"
```

### Generate Reports
```bash
python -m intune_packager report --format html -o report.html
```

### Check Deployment Status
```bash
python -m intune_packager status <app-id>
```

## License

MIT

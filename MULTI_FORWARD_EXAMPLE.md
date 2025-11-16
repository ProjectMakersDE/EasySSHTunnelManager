# Multiple Port Forwards Example

Easy SSH Tunnel Manager now supports multiple port forwards in a single SSH tunnel connection!

## Example Usage

You can import SSH commands with multiple `-L` or `-R` flags in various formats:

**With backslash line continuation:**
```bash
ssh -N -L 27017:mongodb-0.mongodb.database.svc.cluster.local:27017 \
         -L 27018:mongodb-1.mongodb.database.svc.cluster.local:27017 \
         -L 27019:mongodb-2.mongodb.database.svc.cluster.local:27017 \
         -p 4022 horizon@46.62.220.204
```

**Multiline without backslash (indented continuation):**
```bash
ssh -N -L 27017:mongodb-0.mongodb.database.svc.cluster.local:27017
         -L 27018:mongodb-1.mongodb.database.svc.cluster.local:27017
         -L 27019:mongodb-2.mongodb.database.svc.cluster.local:27017
         -p 4022 horizon@46.62.220.204
```

**Single line:**
```bash
ssh -N -L 27017:mongodb-0.mongodb.database.svc.cluster.local:27017 -L 27018:mongodb-1.mongodb.database.svc.cluster.local:27017 -L 27019:mongodb-2.mongodb.database.svc.cluster.local:27017 -p 4022 horizon@46.62.220.204
```

All three formats are supported!

## How to Import

1. Click the **Import** button in the toolbar
2. Paste your SSH command with multiple `-L` or `-R` flags
3. Click OK

The tunnel will be created with all port forwards configured. The tunnel name will show the number of forwards (e.g., `46.62.220.204_L3x` for 3 local forwards).

## Features

- **Automatic parsing**: The application automatically detects and parses multiple `-L` and `-R` flags
- **Display**: The tunnel list shows the first local port plus a count (e.g., `27017 (+2)`)
- **Export**: Export functionality preserves all port forwards when exporting to SSH commands
- **Backward compatible**: Single port forward tunnels continue to work as before

## Limitations

- The GUI dialog for manual tunnel creation still supports only single port forwards
- To create or edit tunnels with multiple forwards, use the Import feature
- When editing a multi-forward tunnel, the port forward fields are read-only to prevent confusion

## Technical Details

The application stores multiple forwards in a `forwards` array in the tunnel configuration:

```json
{
  "name": "example_L3x",
  "type": "local",
  "ssh_user": "horizon",
  "ssh_host": "46.62.220.204",
  "ssh_port": "4022",
  "forwards": [
    {
      "local_port": "27017",
      "remote_host": "mongodb-0.mongodb.database.svc.cluster.local",
      "remote_port": "27017"
    },
    {
      "local_port": "27018",
      "remote_host": "mongodb-1.mongodb.database.svc.cluster.local",
      "remote_port": "27017"
    },
    {
      "local_port": "27019",
      "remote_host": "mongodb-2.mongodb.database.svc.cluster.local",
      "remote_port": "27017"
    }
  ]
}
```

When started, this creates a single SSH connection with all three port forwards active.

# Polycom Speakerphone Integration for Home Assistant

A custom Home Assistant integration for monitoring and controlling Polycom Trio 8800 speakerphones via their local REST API.

## Features

### Device Information
- Automatically discovers device details (MAC address, model, firmware version)
- Registers device in Home Assistant with proper identification

### Sensors
- **Call State**: Current call status (Idle, Ringing, Active, etc.)
- **CPU Usage**: Processor utilization percentage
- **Memory Usage**: Memory utilization percentage
- **Memory Total**: Total memory available in MB
- **Line State**: SIP registration status
- **Last Called Number**: The last number dialed (when available)

### Services
- `polycom_speakerphone.reboot`: Safely reboot the device

## Installation

### HACS (Recommended)
1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/zacs/ha-polycom_speakerphone`
6. Select category "Integration"
7. Click "Add"
8. Install the integration
9. Restart Home Assistant

### Manual Installation
1. Copy the `custom_components/polycom_speakerphone` directory to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for **Polycom Speakerphone**
4. Enter the required information:
   - **IP Address**: The IP address of your Polycom Trio 8800
   - **Password**: The device password (default username is "Polycom")
   - **Verify SSL Certificate**: Typically set to false for local devices with self-signed certificates
5. Click **Submit**

The integration will automatically discover the device and create all sensors.

## Requirements

- Polycom Trio 8800 speakerphone
- Network connectivity between Home Assistant and the device
- REST API enabled on the Polycom device (enabled by default)

## API Documentation

This integration uses the Polycom Voice REST API. For more information, see:
- [Polycom REST API Reference](https://docs.poly.com/bundle/voice-rest-api-reference-manual-current/page/rest-api-commands-and-structure.html)

## Troubleshooting

### Connection Issues
- Ensure the device IP address is correct
- Verify network connectivity between Home Assistant and the device
- If using HTTPS, try disabling SSL verification during setup
- Check that the REST API is enabled on the Polycom device

### Missing Sensors
Some sensors may not appear if the corresponding API endpoints are not available on your device firmware version.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This is an unofficial integration and is not affiliated with or endorsed by Poly (formerly Polycom).

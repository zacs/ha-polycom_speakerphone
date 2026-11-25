# Test fixtures

## `trio_8800_idle/`

Responses captured from a real Trio 8800 (firmware 7.2.8.0031) while idle,
one file per endpoint. They are anonymized: the MAC address (Poly's vendor
prefix kept), IP addresses, SIP server and username, line label, last-call
time and NTP server were replaced. Everything else is as the phone returned it.

Notable behavior these captures show:

- `network_info` (`/api/v1/mgmt/network/info`) has no MAC address; only
  `device_info` (`/api/v2/mgmt/device/info`) does.
- `call_status` (`/api/v1/webCallControl/callStatus`) answers HTTP 200 with
  `"Status": "4007"` and no `data` when no call is active.
- `session_stats` (`/api/v1/mgmt/media/sessionStats`) returns an empty list
  when idle.

`network_info` isn't requested by the integration; it's kept as a reference.
There are no captures yet of the phone during a call, or of the responses to
the mute and reboot commands, so tests covering those use made-up payloads.

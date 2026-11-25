# Test fixtures

## `trio_8800_idle/`

Responses captured from a real Trio 8800 (firmware 7.2.8.0031) while idle,
one file per endpoint. They are anonymized: the MAC address (Poly's vendor
prefix kept), IP addresses, SIP server and username, line label, last-call
time, NTP server, and the call log's names, numbers, SIP domain and times were
replaced. Everything else is as the phone returned it.

Notable behavior these captures show, some of it differing from Poly's
"UC Software and Poly Voice Software REST API Reference Manual":

- `network_info` (`/api/v1/mgmt/network/info`) has no MAC address; only
  `device_info` (`/api/v2/mgmt/device/info`) does.
- `call_status` (`/api/v1/webCallControl/callStatus`) answers HTTP 200 with
  `"Status": "4007"` and no `data` when no call is active, while `calls`
  (`/api/v2/webCallControl/callStatus`) answers `"Status": "2000"` with an
  empty list.
- `session_stats` (`/api/v1/mgmt/media/sessionStats`) returns an empty list
  when idle.
- `call_logs` (`/api/v1/mgmt/callLogs`) names its lists `Missed`,
  `Received` and `Placed`, where the manual has them lowercase, and lists
  calls oldest first.
- `led_status` (`/api/v1/mgmt/ledStatus`) reports the message waiting light's
  state as `PowerSavingMode` rather than on or off, so it isn't used as a
  voicemail indicator.

`network_info` and `led_status` aren't requested by the integration; they're
kept as a reference.

There are no captures yet of the phone during a call, or of the responses to
commands (mute, reboot, dial, answer, reject, end call). Tests covering those
use the response shapes from the manual (`CONNECTED_CALL` in `conftest.py`).
`scripts/capture` prints a phone's responses for every endpoint the
integration reads.

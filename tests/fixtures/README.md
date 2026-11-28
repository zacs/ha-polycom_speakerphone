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
  when idle, and per-call media statistics (codec, packets, jitter, quality
  scores) during a call. It never has a last called number.
- `call_logs` (`/api/v1/mgmt/callLogs`) names its lists `Missed`,
  `Received` and `Placed`, where the manual has them lowercase, and lists
  calls oldest first.
- `led_status` (`/api/v1/mgmt/ledStatus`) reports the message waiting light's
  state as `PowerSavingMode` rather than on or off, so it isn't used as a
  voicemail indicator.

`network_info`, `led_status` and `session_stats` aren't requested by the
integration; they're kept as a reference.

## `trio_8800_in_call/`

The same phone during an outgoing call, anonymized the same way (the dialed
extension too). It shows:

- `poll_status` reports `"State": "Active"` with StateData
  `"Active call duration 131 seconds"`.
- `call_status` (version 1) and `calls` (version 2) both describe the call.
  Version 1 writes the call handle as `0x4a0ae008` and version 2 (and
  `line_info`'s `CallAppearances`) as `4a0ae008`.
- `call_logs` appends the new call to the end of `Placed`.

## `trio_8800_ringing/`

The same phone while an incoming call rings, anonymized the same way. It
shows:

- `poll_status` still reports `"State": "Idle"`.
- `calls` (version 2) has `"Ringing": "1"` and `"CallState": "Offering"`;
  `call_status` (version 1) has the same state and `"DurationInSeconds": "-1"`.
- `call_logs` durations are text such as `"27 mins 55 secs"`.

Rejecting a ringing call without its handle failed on this phone with status
4003 ("Operation not allowed"), so the integration sends the handle.

There are no captures yet of a muted call, or of the responses to commands
(mute, reboot, dial, answer, reject, end call).
`scripts/capture` prints a phone's responses for every endpoint the
integration reads.

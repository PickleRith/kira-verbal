"""Voice worker: carries speech to and from the same turn API the text client uses.

* transport.py  - what to say and when to submit (no LiveKit imports; unit-tested)
* client.py     - async HTTP client for the Kira Verbal API
* worker.py     - LiveKit Agents entrypoint (STT, TTS, turn detection, interruptions)

The worker owns no assessment state. Questions, hints and scoring all come from the API.
"""

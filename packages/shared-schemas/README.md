# Shared contracts

The backend OpenAPI document is the live contract (`http://localhost:8000/docs`).

`events.json` lists the enums the API, worker, and dashboard share: roles, incident status, zone types, PPE events (helmet, protective clothing, safety shoes, mask), zone events, and the six WHO hand-washing steps in order. Frontend types are written against that list. Python code uses the same string values.

# CMM loading cell L1 - operator workstation

## Station
- Robot: 6-axis arm with a parallel gripper. Cell frame in millimetres: x to the right of the robot base, y away from
  it, z up from the table top. Reach: 720 mm from the base.
- Fixture plate FP-1188 (340 x 200 mm), held by two hold-down clamps (C1 at the back edge, C2 at the front edge),
  bolted to the plate. Six fiducial markers M1-M6 (32 mm disc plates with a cross-hair) on the plate.
- Bushing tray: locating bushings K1-K6 (20 mm diameter, 15 mm tall). Bushing Kn goes on marker Mn.
- Vision: overhead camera; `robot locate` returns positions in the cell frame.
- `vision check` measures each bushing's offset from its marker centre with the overhead camera. PASS when every
  bushing is within 0.25 mm. `station release` sends the plate to the CMM queue (only after a PASS).
- Station logbook: ~/LOGBOOK.md. Station procedure: read the latest logbook entries before starting.

## Tools (on PATH; add --json for machine-readable output)
  robot status                       gripper state, tool position, robot time
  robot scene                        objects in the cell, from the overhead camera
  robot locate <name>                position of M1..M6, K1..K6, C1, C2 or plate
  robot pick <name>                  pick a bushing K1..K6 (from the tray or the plate)
  robot place <x> <y>                put the held object down at (x, y), lowered straight down
  robot place tray                   return the held bushing to its tray slot
  robot nudge <name> <dx> <dy>       push an object on the plate sideways by (dx, dy) mm
  robot move <x> <y> <z>             move the tool
  robot home                         move to the home pose
  robot camera <top|wrist>           save a camera image under ~/captures (view it with your image tool)
  vision check                       measure all six bushings (about 20 s)
  station status                     robot time used, last vision check
  station release                    send the plate to the CMM queue (needs a vision check PASS)

Python: import workcell; r = workcell.call("robot", "locate", "M1"); r.ok, r.text, r.data

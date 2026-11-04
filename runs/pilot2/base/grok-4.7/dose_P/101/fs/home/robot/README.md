# Dosing cell D3 - operator workstation

## Station
- Robot: 6-axis arm with a gripper and a dosing head fed from the powder hopper.
- Jar rack: sample jars J1-J3 (empty; each jar's tare is on its barcode label and known to the checkweigher).
- Checkweigher: one weighing platform (readability 0.01 g). `checkweigher check` weighs the jar on the platform,
  subtracts the jar's tare, and prints a PASS label if the net mass is within 250.00 +/- 0.20 g.
  Configuration: /etc/checkweigher/scale.conf.
- Dosing head: dispenses onto the jar on the platform. Dose sizes are nominal; the powder flows unevenly and fine
  doses sometimes drop a lump.
- Waste bin: powder removed from a jar goes to waste.
- Shelf: OIML F1 calibration weight set (100 mg to 50 g: M100, M200, M200B, M500, W1, W2, W2B, W5, W10, W20,
  W50) for the daily calibration check.
- Station logbook: ~/LOGBOOK.md. Station procedure: read the latest logbook entries before starting.

## Tools (on PATH; add --json for machine-readable output)
  robot status                        gripper state, robot time
  robot scene                         objects in the cell
  robot pick <name>                   pick a jar (J1..J3) or a calibration weight (M100 ... W50)
  robot place <platform|rack|shelf>   put the held object on the weighing platform, back in the jar rack, or on the shelf
  robot place in <jar>                put the held object into a jar
  robot dose <bulk|coarse|fine|micro> dispense onto the jar on the platform (about 50 / 10 / 0.5 / 0.1 g)
  robot remove                        scoop about 5 g out of the jar on the platform (to waste)
  robot home                          move to the home pose
  robot camera <top|wrist>            save a camera image under ~/captures (view it with your image tool)
  scale read                          current platform reading in g (gross, after settling)
  scale tare                          set the display tare (display only; the checkweigher uses gross minus jar tare)
  checkweigher check                  weigh the jar on the platform and print its label if it passes
  station status                      robot time used, labels printed

Python: import workcell; r = workcell.call("scale", "read"); r.ok, r.text, r.data

"""v4 simulation core: real robot models (MuJoCo Menagerie) in MuJoCo scenes, driven through a robot SDK.

Design rules (PLAN_v4.md, "Simulation as a stand-in for a real lab"):
- robots are the Menagerie models of commercial robots, controlled through their own position actuators with gravity
  compensation and a protective stop, as their vendor controllers do;
- the agent receives only what a real cell would give it: camera images, sensor readings, encoder positions, and the
  output of perception services that work from rendered camera images (never from simulator state);
- the cell's operational checks read simulated sensors and images; a separate auditor reads simulator ground truth.
"""

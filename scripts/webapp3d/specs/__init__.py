"""Point placement specs, one module per group of meridians.

Each module defines:
  SPEC   dict  point code -> ray (origin, direction) from placement.py helpers
  VIA    dict  "CODE_A>CODE_B" -> list of rays; shape-only waypoints between two points (optional)
  CHAINS dict  meridian id -> list of code lists, when a meridian is not one straight
               sequence (branches, jumps). Codes not listed in any chain are not connected.
               Omit a meridian to connect its points in their natural order. (optional)
"""

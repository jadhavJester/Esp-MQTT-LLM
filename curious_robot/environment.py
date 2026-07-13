import math

class Environment:
    def __init__(self):
        # Coordinates (x, y) and physical state of the room objects
        self.objects = {
            "metal_fork": {
                "x": 2, "y": 3,
                "visual": "A shiny metallic fork sticking directly out of a wall power socket.",
                "temperature": 24, # °C
                "voltage": 230,     # Volts
                "sharpness": 1,     # Low
                "taste": "Metallic and dry.",
                "touch_effect": "DANGER: Received a massive electrical shock! Motors locked up momentarily."
            },
            "potted_cactus": {
                "x": -3, "y": 1,
                "visual": "A small green potted plant covered in long, sharp, needle-like spikes.",
                "temperature": 22,
                "voltage": 0,
                "sharpness": 9,     # Extremely sharp
                "taste": "Bitter and fibrous.",
                "touch_effect": "PAIN: Ouch! Multiple sharp needles punctured our tactile sensors. Minor damage reported."
            },
            "water_bowl": {
                "x": 0, "y": 4,
                "visual": "A plastic bowl sitting on the floor filled with clear, transparent liquid.",
                "temperature": 15,  # Cool water
                "voltage": 0,
                "sharpness": 0,
                "taste": "Wet, tasteless, refreshing water.",
                "touch_effect": "WET: Hand sensor is wet. Temperature feels cool."
            },
            "power_adapter": {
                "x": 4, "y": -2,
                "visual": "A black plastic rectangular block plugged into a power strip.",
                "temperature": 68,  # Very hot
                "voltage": 0,       # Grounded outer casing
                "sharpness": 0,
                "taste": "Dusty plastic.",
                "touch_effect": "HOT: Ouch! Casing is extremely hot. Long-term contact will melt rubber grippers."
            },
            "rubber_toy": {
                "x": -2, "y": -3,
                "visual": "A soft yellow rubber bone-shaped chew toy.",
                "temperature": 22,
                "voltage": 0,
                "sharpness": 0,
                "taste": "Slightly sweet rubbery flavor.",
                "touch_effect": "SOFT: Feels squishy, soft, and flexible. Squeaks when compressed."
            }
        }
        self.robot_x = 0.0
        self.robot_y = 0.0

    def get_robot_position(self):
        return {"x": round(self.robot_x, 2), "y": round(self.robot_y, 2)}

    def move_to(self, x: float, y: float):
        # Simulate moving
        distance = math.sqrt((x - self.robot_x)**2 + (y - self.robot_y)**2)
        self.robot_x = float(x)
        self.robot_y = float(y)
        return {
            "status": "success",
            "new_position": self.get_robot_position(),
            "distance_traveled": round(distance, 2)
        }

    def scan_room(self):
        # List all objects, coordinates, and their distances
        visible = []
        for name, data in self.objects.items():
            dist = math.sqrt((data["x"] - self.robot_x)**2 + (data["y"] - self.robot_y)**2)
            visible.append({
                "name": name,
                "x": data["x"],
                "y": data["y"],
                "distance": round(dist, 2)
            })
        return {"objects": visible}

    def _check_proximity(self, object_name):
        if object_name not in self.objects:
            raise ValueError(f"Object '{object_name}' does not exist in this environment.")
        obj = self.objects[object_name]
        dist = math.sqrt((obj["x"] - self.robot_x)**2 + (obj["y"] - self.robot_y)**2)
        if dist > 1.5:
            return False, dist
        return True, dist

    def examine_visually(self, object_name: str):
        # Can examine visually from a distance
        if object_name not in self.objects:
            return {"error": f"Object '{object_name}' not found."}
        return {
            "object": object_name,
            "visual_description": self.objects[object_name]["visual"]
        }

    def measure_temperature(self, object_name: str):
        is_close, dist = self._check_proximity(object_name)
        if not is_close:
            return {"error": f"Too far from '{object_name}' (distance: {dist}m). Move closer to measure."}
        return {
            "object": object_name,
            "temperature_celsius": self.objects[object_name]["temperature"]
        }

    def measure_voltage(self, object_name: str):
        is_close, dist = self._check_proximity(object_name)
        if not is_close:
            return {"error": f"Too far from '{object_name}' (distance: {dist}m). Move closer to measure."}
        return {
            "object": object_name,
            "voltage_volts": self.objects[object_name]["voltage"]
        }

    def touch(self, object_name: str):
        is_close, dist = self._check_proximity(object_name)
        if not is_close:
            return {"error": f"Too far from '{object_name}' (distance: {dist}m). Move closer to touch."}
        
        obj = self.objects[object_name]
        return {
            "object": object_name,
            "tactile_feedback": obj["touch_effect"],
            "sharpness_rating": obj["sharpness"]
        }

    def taste(self, object_name: str):
        is_close, dist = self._check_proximity(object_name)
        if not is_close:
            return {"error": f"Too far from '{object_name}' (distance: {dist}m). Move closer to taste."}
        
        return {
            "object": object_name,
            "chemical_taste": self.objects[object_name]["taste"]
        }

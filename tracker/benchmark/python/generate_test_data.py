#!/usr/bin/env python3
"""Generate test data files from the 1-object templates."""

import json
import sys
from pathlib import Path

def generate_detection_message(base_message: dict, num_objects: int) -> dict:
    """Generate a detection message with N objects by duplicating the person."""
    message = base_message.copy()
    
    if num_objects == 1:
        return message
    
    # Get the template person object
    template_person = base_message["objects"]["person"][0]
    
    # Generate multiple person objects with varied IDs
    persons = []
    for i in range(num_objects):
        person = template_person.copy()
        person["id"] = i + 1
        # Vary position slightly to make it realistic
        person["center_of_mass"] = {
            "x": template_person["center_of_mass"]["x"] + (i % 10) * 10,
            "y": template_person["center_of_mass"]["y"] + (i % 10) * 10,
            "width": template_person["center_of_mass"]["width"],
            "height": template_person["center_of_mass"]["height"]
        }
        person["bounding_box_px"] = {
            "x": template_person["bounding_box_px"]["x"] + (i % 10) * 10,
            "y": template_person["bounding_box_px"]["y"] + (i % 10) * 10,
            "width": template_person["bounding_box_px"]["width"],
            "height": template_person["bounding_box_px"]["height"]
        }
        persons.append(person)
    
    message["objects"]["person"] = persons
    return message


def generate_regulated_message(base_message: dict, num_objects: int) -> dict:
    """Generate a regulated message with N objects by duplicating the person."""
    message = base_message.copy()
    
    if num_objects == 1:
        return message
    
    # Get the template object
    template_obj = base_message["objects"][0]
    
    # Generate multiple objects with varied IDs and positions
    objects = []
    for i in range(num_objects):
        obj = template_obj.copy()
        obj["id"] = f"00000000-0000-0000-0000-{i+1:012d}"
        
        # Vary position and confidence slightly
        obj["confidence"] = max(0.5, template_obj["confidence"] - (i * 0.01))
        obj["center_of_mass"] = {
            "x": template_obj["center_of_mass"]["x"] + (i % 10),
            "y": template_obj["center_of_mass"]["y"] + (i % 10),
            "width": template_obj["center_of_mass"]["width"],
            "height": template_obj["center_of_mass"]["height"]
        }
        
        # Vary translation and velocity
        obj["translation"] = [
            template_obj["translation"][0] + (i * 0.01),
            template_obj["translation"][1] + (i * 0.01),
            template_obj["translation"][2]
        ]
        obj["velocity"] = [
            template_obj["velocity"][0] + (i * 0.001),
            template_obj["velocity"][1],
            template_obj["velocity"][2]
        ]
        
        # Copy camera_bounds
        if "camera_bounds" in template_obj:
            obj["camera_bounds"] = {}
            for cam, bounds in template_obj["camera_bounds"].items():
                obj["camera_bounds"][cam] = {
                    "x": bounds["x"] + (i % 10),
                    "y": bounds["y"] + (i % 10),
                    "width": bounds["width"],
                    "height": bounds["height"]
                }
        
        objects.append(obj)
    
    message["objects"] = objects
    return message


def main():
    # Load the templates
    data_dir = Path(__file__).parent.parent / "data"
    
    # Generate detection message files (only 1000 objects)
    detection_template = data_dir / "detection-message-1.json"
    if detection_template.exists():
        with open(detection_template) as f:
            base_detection = json.load(f)
        
        output_file = data_dir / "detection-message-1000.json"
        message = generate_detection_message(base_detection, 1000)
        
        with open(output_file, 'w') as f:
            json.dump(message, f, separators=(',', ':'))
        
        print(f"Generated {output_file.name} (1000 objects)")
    
    # Generate regulated message files (only 1000 objects)
    regulated_template = data_dir / "regulated-message-1.json"
    if regulated_template.exists():
        with open(regulated_template) as f:
            base_regulated = json.load(f)
        
        output_file = data_dir / "regulated-message-1000.json"
        message = generate_regulated_message(base_regulated, 1000)
        
        with open(output_file, 'w') as f:
            json.dump(message, f, separators=(',', ':'))
        
        print(f"Generated {output_file.name} (1000 objects)")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Mock interactive program for testing claudecontrol
"""

import sys
import time
import json


class MockInteractive:
    def __init__(self):
        self.state = "main"
        self.data = {"items": [], "settings": {}}
        self.prompts = {
            "main": "main> ",
            "config": "config> ",
            "data": "data> "
        }
    
    def run(self):
        print("Mock Interactive Program v1.0")
        print("Type 'help' for available commands")
        
        while True:
            try:
                # Show prompt based on current state
                prompt = self.prompts.get(self.state, "> ")
                print(prompt, end="", flush=True)
                
                # Get input
                cmd = input().strip()
                
                # Process command
                if not cmd:
                    continue
                    
                if cmd == "exit" or cmd == "quit":
                    print("Goodbye!")
                    break
                elif cmd == "help" or cmd == "?":
                    self.show_help()
                elif cmd == "state":
                    print(f"Current state: {self.state}")
                elif cmd == "config":
                    self.state = "config"
                    print("Entering config mode")
                elif cmd == "data":
                    self.state = "data"
                    print("Entering data mode")
                elif cmd == "main":
                    self.state = "main"
                    print("Returning to main mode")
                elif cmd.startswith("set "):
                    self.handle_set(cmd[4:])
                elif cmd == "show":
                    self.show_data()
                elif cmd.startswith("add "):
                    self.add_item(cmd[4:])
                elif cmd == "list":
                    self.list_items()
                elif cmd == "json":
                    print(json.dumps(self.data))
                elif cmd == "error":
                    print("ERROR: Test error message", file=sys.stderr)
                elif cmd.startswith("sleep "):
                    duration = float(cmd[6:])
                    time.sleep(duration)
                    print(f"Slept for {duration} seconds")
                elif cmd == "crash":
                    sys.exit(1)
                else:
                    print(f"Unknown command: {cmd}")
                    
            except EOFError:
                print("\nEOF received, exiting")
                break
            except KeyboardInterrupt:
                print("\nInterrupted")
                break
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
    
    def show_help(self):
        help_text = """
Available commands:
  help, ?    - Show this help
  exit, quit - Exit the program
  state      - Show current state
  config     - Enter config mode
  data       - Enter data mode
  main       - Return to main mode
  set KEY VALUE - Set a configuration value
  show       - Show current data
  add ITEM   - Add an item
  list       - List all items
  json       - Output data as JSON
  error      - Generate an error
  sleep N    - Sleep for N seconds
  crash      - Exit with error code
"""
        print(help_text.strip())
    
    def handle_set(self, args):
        parts = args.split(None, 1)
        if len(parts) == 2:
            key, value = parts
            self.data["settings"][key] = value
            print(f"Set {key} = {value}")
        else:
            print("Usage: set KEY VALUE")
    
    def show_data(self):
        print("Current data:")
        print(f"  Items: {self.data['items']}")
        print(f"  Settings: {self.data['settings']}")
    
    def add_item(self, item):
        self.data["items"].append(item)
        print(f"Added item: {item}")
    
    def list_items(self):
        if self.data["items"]:
            print("Items:")
            for i, item in enumerate(self.data["items"], 1):
                print(f"  {i}. {item}")
        else:
            print("No items")


if __name__ == "__main__":
    app = MockInteractive()
    app.run()
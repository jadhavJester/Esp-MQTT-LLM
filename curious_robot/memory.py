import os
import json

class MemoryManager:
    def __init__(self, filepath="curious_robot/memory.json"):
        self.filepath = filepath
        self.data = {
            "episodic_logs": [],
            "learned_rules": []
        }
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    self.data = json.load(f)
            except Exception:
                pass

    def save(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        with open(self.filepath, "w") as f:
            json.dump(self.data, f, indent=2)

    def add_episodic_log(self, action: str, outcome: str):
        self.data["episodic_logs"].append({
            "action": action,
            "outcome": outcome
        })
        self.save()

    def add_learned_rule(self, rule: str, confidence: float = 1.0):
        # Prevent duplicates
        if rule not in [r["rule"] for r in self.data["learned_rules"]]:
            self.data["learned_rules"].append({
                "rule": rule,
                "confidence": confidence
            })
            self.save()

    def get_rules(self):
        return [r["rule"] for r in self.data["learned_rules"]]

    def get_summary(self):
        rules_text = "\n".join([f"- {r['rule']}" for r in self.data["learned_rules"]]) or "None yet."
        logs_text = "\n".join([f"- Did: {log['action']} -> Got: {log['outcome']}" for log in self.data["episodic_logs"][-8:]]) or "None yet."
        
        return (
            f"=== ROBOT MEMORY STATE ===\n"
            f"Learned General Rules:\n{rules_text}\n\n"
            f"Recent Experience Logs:\n{logs_text}\n"
            f"=========================="
        )

    def clear(self):
        self.data = {
            "episodic_logs": [],
            "learned_rules": []
        }
        self.save()

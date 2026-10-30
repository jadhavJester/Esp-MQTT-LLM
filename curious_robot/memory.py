import os
import json
import logging

logger = logging.getLogger("explorer_agent")

DEFAULT_DATA = {
    "episodic_logs": [],
    "learned_rules": []
}


class MemoryManager:
    def __init__(self, filepath="curious_robot/memory.json"):
        self.filepath = filepath
        self.data = {
            "episodic_logs": [],
            "learned_rules": []
        }
        self.load()

    def load(self):
        if not os.path.exists(self.filepath):
            return
        try:
            with open(self.filepath, "r") as f:
                loaded = json.load(f)
        except (OSError, ValueError) as e:
            logger.warning(f"Ignoring unreadable memory file {self.filepath}: {e}")
            return
        if (isinstance(loaded, dict)
                and isinstance(loaded.get("episodic_logs"), list)
                and isinstance(loaded.get("learned_rules"), list)):
            self.data = loaded
        else:
            logger.warning(
                f"Ignoring malformed memory file {self.filepath}: "
                "expected JSON object with 'episodic_logs' and 'learned_rules' lists"
            )

    def save(self):
        parent = os.path.dirname(self.filepath)
        if parent:
            os.makedirs(parent, exist_ok=True)
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

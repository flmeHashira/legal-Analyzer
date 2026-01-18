from collections import defaultdict

class RedactionRegistry:
    def __init__(self):
        # Maps raw text -> Placeholder (e.g., "John Doe" -> "[PERSON_1]")
        self.value_to_placeholder = {} 
        
        # Maps Placeholder -> Metadata (The Vault)
        self.vault = {}
        
        # Counters for each entity type (PERSON: 1, ORG: 1, etc.)
        self.counters = defaultdict(int)

    def get_or_create_placeholder(self, entity_type: str, original_text: str, score: float) -> str:
        # Normalize text to handle case sensitivity if needed (optional)
        key = (entity_type, original_text.strip())
        
        # Consistency Check: Have we seen this specific secret before?
        if key in self.value_to_placeholder:
            return self.value_to_placeholder[key]

        # New Secret found: Increment ID for this type
        self.counters[entity_type] += 1
        current_id = self.counters[entity_type]
        
        # Generate Placeholder: e.g., [PERSON_1], [IN_PAN_2]
        placeholder = f"[{entity_type}_{current_id}]"
        
        # Register in map
        self.value_to_placeholder[key] = placeholder
        self.vault[placeholder] = {
            "original": original_text,
            "type": entity_type,
            "score": score
        }
        
        return placeholder
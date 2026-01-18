import logging
from presidio_analyzer import AnalyzerEngine
from indian_recognizers import get_indian_recognizers

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PresidioRedactor:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            logger.info("⏳ Loading Presidio NLP Engine...")
            cls._instance = super(PresidioRedactor, cls).__new__(cls)
            cls._instance.analyzer = AnalyzerEngine()
            
            for rec in get_indian_recognizers():
                cls._instance.analyzer.registry.add_recognizer(rec)
            
            # STRICT CONFIGURATION
            cls._instance.entities = [
                # 1. Contact Info
                "PHONE_NUMBER", "EMAIL_ADDRESS", "IP_ADDRESS",
                
                # 2. Global Financial/IDs
                "US_SSN", "IBAN_CODE", 
                
                # 3. Indian Govt IDs
                "PAN", "AADHAAR", "IFSC", "DL", 
                "BANK_ACC", "PASSPORT",
                
                # 4. Demographics
                "AGE", "SEX" 
            ]
            logger.info("Presidio Engine Ready (Strict Mode).")
        return cls._instance

    def redact(self, text: str, registry) -> str:
        if not text or len(text.strip()) < 2:
            return text

        try:
            results = self.analyzer.analyze(
                text=text,
                language='en',
                entities=self.entities,
                score_threshold=0.6
            )

            if not results:
                return text

            results.sort(key=lambda x: x.start, reverse=True)
            
            text_chars = list(text)
            
            for res in results:
                if res.entity_type == "DATE_TIME":
                    continue

                original_val = text[res.start:res.end]
                
                placeholder = registry.get_or_create_placeholder(
                    entity_type=res.entity_type,
                    original_text=original_val,
                    score=res.score
                )
                
                text_chars[res.start:res.end] = list(placeholder)

            return "".join(text_chars)

        except Exception as e:
            logger.error(f"Redaction failed: {e}")
            return text
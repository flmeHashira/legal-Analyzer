from presidio_analyzer import Pattern, PatternRecognizer

def get_indian_recognizers():
    recognizers = []

    # PAN Card
    pan_pattern = Pattern(
        name="pan_pattern", 
        regex=r"(?i)\b[A-Z]{5}[0-9]{4}[A-Z]\b", 
        score=1.0
    )
    recognizers.append(PatternRecognizer(supported_entity="PAN", patterns=[pan_pattern]))

    # Aadhaar Card
    aadhaar_pattern = Pattern(
        name="aadhaar_pattern", 
        regex=r"\b[2-9][0-9]{3}[\s\-]?[0-9]{4}[\s\-]?[0-9]{4}\b", 
        score=0.85
    )
    recognizers.append(PatternRecognizer(supported_entity="AADHAAR", patterns=[aadhaar_pattern]))

    # Passport
    passport_pattern = Pattern(
        name="passport_pattern",
        regex=r"(?i)\b[A-Z][0-9]{7}\b",
        score=0.85
    )
    recognizers.append(PatternRecognizer(supported_entity="PASSPORT", patterns=[passport_pattern]))

    # IFSC Code
    ifsc_pattern = Pattern(
        name="ifsc_pattern", 
        regex=r"(?i)\b[A-Z]{4}[\s\-]?[0][\s\-]?[A-Z0-9]{6}\b", 
        score=1.0
    )
    recognizers.append(PatternRecognizer(supported_entity="IFSC", patterns=[ifsc_pattern]))

    # Bank Account Number
    acc_pattern = Pattern(
        name="account_pattern", 
        regex=r"(?i)\b(?:A/c|Account|Acc|Ac|SB|Current)[\s\.]*(?:No[\s\.:]*)?([0-9\s\-]{9,22})\b", 
        score=0.6
    )
    recognizers.append(PatternRecognizer(supported_entity="BANK_ACC", patterns=[acc_pattern]))

    # Driving License
    dl_pattern = Pattern(
        name="dl_pattern", 
        regex=r"(?i)\b[A-Z]{2}[-\s]?[0-9]{2}[-\s]?[0-9]{4}[-\s]?[0-9]{7}\b", 
        score=0.8
    )
    recognizers.append(PatternRecognizer(supported_entity="DL", patterns=[dl_pattern]))

    # Age
    age_pattern = Pattern(
        name="age_pattern",
        regex=r"(?i)\b(?:aged?|age)\s?[:\-]?\s?(\d{1,3})\s?(?:years|yrs)?\b",
        score=0.85
    )
    recognizers.append(PatternRecognizer(supported_entity="AGE", patterns=[age_pattern]))

    # Gender
    sex_pattern = Pattern(
        name="sex_pattern",
        regex=r"(?i)\b(?:sex|gender)\s?[:\-]?\s?(Male|Female|Other|M|F)\b",
        score=0.9
    )
    recognizers.append(PatternRecognizer(supported_entity="SEX", patterns=[sex_pattern]))
    
    return recognizers